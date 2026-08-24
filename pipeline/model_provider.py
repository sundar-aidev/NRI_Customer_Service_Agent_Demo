"""Model provider backed by the user's local ChatGPT-authenticated Codex client."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Any, Protocol


class ModelProviderError(RuntimeError):
    """Safe provider failure; never includes OAuth tokens."""


class JsonModelProvider(Protocol):
    @property
    def metadata(self) -> dict[str, Any]: ...

    def generate_json(
        self, purpose: str, prompt: str, schema: dict[str, Any]
    ) -> dict[str, Any]: ...


class CodexOAuthProvider:
    """Run schema-constrained Codex turns using the existing ChatGPT login.

    The provider delegates credential storage and refresh entirely to Codex.
    No OAuth token is read, copied, logged, or passed through this process.
    """

    _semaphore = threading.Semaphore(2)

    def __init__(
        self,
        *,
        executable: str = "codex",
        model: str | None = None,
        timeout_seconds: int | None = None,
    ) -> None:
        resolved = shutil.which(executable)
        if not resolved:
            raise ModelProviderError(f"Codex executable not found: {executable}")
        self.executable = resolved
        self.model = model if model is not None else os.environ.get("NRI_CODEX_MODEL", "")
        self.timeout_seconds = timeout_seconds or int(os.environ.get("NRI_MODEL_TIMEOUT", "180"))

    @property
    def metadata(self) -> dict[str, Any]:
        return {
            "provider": "codex_oauth",
            "model": self.model or "codex_subscription_default",
            "auth": "chatgpt_subscription",
        }

    @classmethod
    def auth_status(cls, executable: str = "codex") -> dict[str, Any]:
        resolved = shutil.which(executable)
        if not resolved:
            return {"available": False, "authenticated": False, "mode": None}
        completed = subprocess.run(
            [resolved, "login", "status"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        combined = f"{completed.stdout}\n{completed.stderr}"
        authenticated = completed.returncode == 0 and "Logged in using ChatGPT" in combined
        return {
            "available": True,
            "authenticated": authenticated,
            "mode": "chatgpt_subscription" if authenticated else None,
        }

    def generate_json(self, purpose: str, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        instruction = (
            "You are a JSON-only component in a customer-support pipeline. "
            "Do not run commands, inspect files, browse, or use tools. Follow the supplied JSON Schema. "
            "Return only the requested structured result.\n\n" + prompt
        )
        with tempfile.TemporaryDirectory(prefix="nri-codex-") as temp_name:
            temp = Path(temp_name)
            schema_path = temp / "schema.json"
            output_path = temp / "output.json"
            schema_path.write_text(json.dumps(schema), encoding="utf-8")
            command = [
                self.executable,
                "exec",
                "--ephemeral",
                "--ignore-user-config",
                "--ignore-rules",
                "--skip-git-repo-check",
                "--sandbox",
                "read-only",
                "--color",
                "never",
                "-c",
                'model_reasoning_effort="low"',
                "--output-schema",
                str(schema_path),
                "--output-last-message",
                str(output_path),
                "--cd",
                str(temp),
            ]
            if self.model:
                command.extend(["--model", self.model])
            command.append("-")
            try:
                with self._semaphore:
                    completed = subprocess.run(
                        command,
                        input=instruction,
                        capture_output=True,
                        text=True,
                        timeout=self.timeout_seconds,
                        check=False,
                    )
            except subprocess.TimeoutExpired as exc:
                raise ModelProviderError(
                    f"Codex {purpose} request timed out after {self.timeout_seconds}s"
                ) from exc
            if completed.returncode != 0:
                detail = (completed.stderr or completed.stdout or "unknown failure").strip()[-1200:]
                raise ModelProviderError(f"Codex {purpose} request failed: {detail}")
            if not output_path.exists():
                raise ModelProviderError(f"Codex {purpose} request produced no structured output")
            try:
                value = json.loads(output_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise ModelProviderError(f"Codex {purpose} output was not valid JSON") from exc
            if not isinstance(value, dict):
                raise ModelProviderError(f"Codex {purpose} output must be a JSON object")
            return value
