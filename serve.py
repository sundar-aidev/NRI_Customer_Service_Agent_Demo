"""Authenticated HTTP server for the five-case NRI evaluation demo.

The deployable surface is deliberately small: five immutable runtime cases,
read-only evidence stores, asynchronous pipeline runs, and human review of a
generated draft. Arbitrary prompts and knowledge mutation are not exposed.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import copy
import hmac
import json
import mimetypes
import os
import re
import sys
import threading
import time
import traceback
import uuid
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from app_data import knowledge_snapshot, record_snapshot
from evals.scorer_v2 import Evaluator
from knowledge.retriever import Document, load_all
from pipeline.fixtures import load_runtime_cases
from pipeline.model_provider import CodexOAuthProvider, ModelProviderError
from pipeline.orchestrator import PipelineFailure, PipelineRunner
from pipeline.verifier import verify_draft
from records.resolver import load_store

ROOT = Path(__file__).resolve().parent
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
STATIC_TEXT_CHARSET_TYPES = {".html", ".htm", ".js", ".mjs", ".css", ".txt"}
STATIC_ASSET_EXTENSIONS = {
    ".css",
    ".js",
    ".mjs",
    ".png",
    ".jpg",
    ".jpeg",
    ".svg",
    ".ico",
    ".woff",
    ".woff2",
}
V2_RUN_ID_RE = re.compile(r"^/api/v2/runs/([^/]+)$")
V2_REVIEW_RE = re.compile(r"^/api/v2/runs/([^/]+)/review$")


def _env_int(name: str, default: int, *, minimum: int = 1) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return value


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    normalized = raw.strip().casefold()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be true or false")


@dataclass(frozen=True)
class Settings:
    host: str
    port: int
    username: str | None
    password: str | None
    auth_required: bool
    max_body_bytes: int = 65_536
    worker_count: int = 2
    max_queued_runs: int = 10
    max_retained_runs: int = 50
    run_limit: int = 60
    run_window_seconds: int = 3_600

    @classmethod
    def from_environment(cls, host: str, port: int) -> "Settings":
        public_bind = host not in {"127.0.0.1", "localhost", "::1"}
        auth_required = _env_bool("NRI_REQUIRE_AUTH", public_bind)
        username = os.environ.get("NRI_DEMO_USERNAME") or None
        password = os.environ.get("NRI_DEMO_PASSWORD") or None
        if auth_required and (not username or not password):
            raise ValueError(
                "NRI_DEMO_USERNAME and NRI_DEMO_PASSWORD are required for a non-local server"
            )
        if auth_required and password is not None and len(password) < 12:
            raise ValueError("NRI_DEMO_PASSWORD must contain at least 12 characters")
        return cls(
            host=host,
            port=port,
            username=username,
            password=password,
            auth_required=auth_required,
            max_body_bytes=_env_int("NRI_MAX_BODY_BYTES", 65_536),
            worker_count=_env_int("NRI_RUN_WORKERS", 2),
            max_queued_runs=_env_int("NRI_MAX_QUEUED_RUNS", 10),
            max_retained_runs=_env_int("NRI_MAX_RETAINED_RUNS", 50),
            run_limit=_env_int("NRI_RUN_LIMIT", 60),
            run_window_seconds=_env_int("NRI_RUN_WINDOW_SECONDS", 3_600),
        )

    @classmethod
    def for_tests(cls, port: int = 0) -> "Settings":
        return cls(
            host=DEFAULT_HOST,
            port=port,
            username=None,
            password=None,
            auth_required=False,
        )


class ApiError(Exception):
    status = 500

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class BadRequest(ApiError):
    status = 400


class Unauthorized(ApiError):
    status = 401


class NotFound(ApiError):
    status = 404


class PayloadTooLarge(ApiError):
    status = 413


class UnsupportedMediaType(ApiError):
    status = 415


class TooManyRequests(ApiError):
    status = 429


class ServiceUnavailable(ApiError):
    status = 503


class SlidingWindowLimiter:
    def __init__(self, limit: int, window_seconds: int) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self.lock = threading.Lock()
        self.events: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        threshold = now - self.window_seconds
        with self.lock:
            events = self.events[key]
            while events and events[0] < threshold:
                events.popleft()
            if len(events) >= self.limit:
                return False
            events.append(now)
            return True


def verify_basic_auth(settings: Settings, header: str) -> bool:
    """Validate one Basic authorization header without logging credentials."""
    if not settings.auth_required:
        return True
    if not header.startswith("Basic "):
        return False
    try:
        decoded = base64.b64decode(header[6:], validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError):
        return False
    username, separator, password = decoded.partition(":")
    if not separator or settings.username is None or settings.password is None:
        return False
    return hmac.compare_digest(username, settings.username) and hmac.compare_digest(
        password,
        settings.password,
    )


def validate_content_length(raw_length: str | None, maximum: int) -> int:
    if raw_length is None:
        return 0
    try:
        length = int(raw_length)
    except ValueError as exc:
        raise BadRequest("invalid Content-Length header") from exc
    if length < 0:
        raise BadRequest("invalid Content-Length header")
    if length > maximum:
        raise PayloadTooLarge("request body is too large")
    return length


class AppState:
    """Read-only source data plus bounded, in-memory demo run state."""

    def __init__(
        self,
        port: int = 0,
        provider: Any | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or Settings.for_tests(port)
        self.port = self.settings.port
        self.lock = threading.RLock()
        self.documents: dict[str, Document] = load_all()
        self.store: dict[str, dict[str, Any]] = load_store()
        self.runtime_cases: list[dict[str, Any]] = load_runtime_cases()
        self.runtime_cases_by_id = {case["id"]: case for case in self.runtime_cases}
        self.v2_runs: dict[str, dict[str, Any]] = {}
        self.executor = ThreadPoolExecutor(
            max_workers=self.settings.worker_count,
            thread_name_prefix="nri-run",
        )
        self.rate_limiter = SlidingWindowLimiter(
            self.settings.run_limit,
            self.settings.run_window_seconds,
        )
        self.provider = provider
        self.provider_error: str | None = None
        if self.provider is None:
            try:
                self.provider = CodexOAuthProvider()
            except ModelProviderError as exc:
                self.provider_error = str(exc)
        self.evaluator = Evaluator()

    def close(self) -> None:
        self.executor.shutdown(wait=False, cancel_futures=True)

    def prune_runs(self) -> None:
        completed = [
            run_id
            for run_id, row in self.v2_runs.items()
            if row["status"] not in {"queued", "running"}
        ]
        overflow = len(self.v2_runs) - self.settings.max_retained_runs + 1
        for run_id in completed[: max(0, overflow)]:
            del self.v2_runs[run_id]


def h_health(state: AppState) -> dict[str, Any]:
    if isinstance(state.provider, CodexOAuthProvider):
        auth = CodexOAuthProvider.auth_status()
    elif state.provider is not None:
        auth = {"available": True, "authenticated": True, "mode": "test"}
    else:
        auth = {"available": False, "authenticated": False, "mode": None}
    return {
        "live": True,
        "case_count": len(state.runtime_cases),
        "pipeline": "query_driven_v2",
        "demo_mode": "fixed_cases",
        "data_mode": "read_only",
        "model_provider": {
            **auth,
            "provider": "codex_oauth",
            "error": state.provider_error,
        },
    }


def h_v2_cases(state: AppState) -> list[dict[str, Any]]:
    return copy.deepcopy(state.runtime_cases)


def _v2_request(state: AppState, body: dict[str, Any]) -> dict[str, Any]:
    allowed_keys = {"case_id", "evaluation_mode"}
    unknown_keys = sorted(set(body) - allowed_keys)
    if unknown_keys:
        raise BadRequest(f"unsupported request field(s): {unknown_keys}")
    case_id = body.get("case_id")
    if not isinstance(case_id, str) or case_id not in state.runtime_cases_by_id:
        raise BadRequest(f"unknown case_id: {case_id!r}")
    if body.get("evaluation_mode", True) is not True:
        raise BadRequest("evaluation_mode cannot be disabled in the hosted demo")
    request = copy.deepcopy(state.runtime_cases_by_id[case_id])
    request["case_id"] = case_id
    request["evaluation_mode"] = True
    return request


def h_v2_start_run(state: AppState, body: dict[str, Any]) -> dict[str, Any]:
    if state.provider is None:
        raise ServiceUnavailable(state.provider_error or "model provider is unavailable")
    request = _v2_request(state, body)
    try:
        PipelineRunner._validate_request(request)
    except PipelineFailure as exc:
        raise BadRequest(str(exc)) from exc

    run_id = f"run_{uuid.uuid4().hex[:12]}"
    trace_id = f"trace_{uuid.uuid4().hex[:12]}"
    with state.lock:
        state.prune_runs()
        pending = sum(row["status"] in {"queued", "running"} for row in state.v2_runs.values())
        if pending >= state.settings.max_queued_runs:
            raise TooManyRequests("the demo run queue is full; try again shortly")
        documents_snapshot = dict(state.documents)
        state.v2_runs[run_id] = {
            "run_id": run_id,
            "trace_id": trace_id,
            "status": "queued",
            "active_stage": "intake",
            "events": [],
            "result": None,
            "error": None,
            "request": copy.deepcopy(request),
            "created_at": time.time(),
        }
        state.executor.submit(
            _execute_v2_run,
            state,
            run_id,
            trace_id,
            request,
            documents_snapshot,
        )
    return {"run_id": run_id, "trace_id": trace_id, "status": "queued"}


def _execute_v2_run(
    state: AppState,
    run_id: str,
    trace_id: str,
    request: dict[str, Any],
    documents_snapshot: dict[str, Document],
) -> None:
    def on_event(event: dict[str, Any]) -> None:
        with state.lock:
            row = state.v2_runs[run_id]
            row["status"] = "running"
            row["active_stage"] = event["stage"]
            row["events"].append(event)

    try:
        runner = PipelineRunner(state.provider, documents_snapshot, state.store)
        result = runner.run(
            request,
            run_id=run_id,
            trace_id=trace_id,
            on_event=on_event,
        )
        terminal_event = None
        if result["trace"] and result["trace"][-1]["stage"] in {"approval", "complete"}:
            terminal_event = result["trace"].pop()
        evaluation = state.evaluator.score(request["case_id"], result)
        result["evaluation"] = evaluation
        result["trace"].append(
            {
                "sequence": len(result["trace"]) + 1,
                "stage": "evaluation",
                "status": "completed" if evaluation["passed"] else "finding",
                "summary": "E1-E5 passed"
                if evaluation["passed"]
                else "One or more critical eval stages failed",
                "elapsed_ms": result["elapsed_ms"],
                "artifact": {
                    key: value["status"]
                    for key, value in evaluation.items()
                    if key.startswith("E") and isinstance(value, dict)
                },
            }
        )
        if not evaluation["passed"]:
            result["status"] = "awaiting_review"
            result["active_stage"] = "approval"
            result["authority"] = {
                **result["authority"],
                "requires_human": True,
                "can_send": False,
                "state": "awaiting_review",
                "reason": result["authority"]["reason"] + "; evaluation finding requires review",
            }
        if terminal_event is not None:
            terminal_event["sequence"] = len(result["trace"]) + 1
            terminal_event["stage"] = result["active_stage"]
            terminal_event["status"] = (
                "awaiting_review" if result["authority"]["requires_human"] else "completed"
            )
            terminal_event["summary"] = result["authority"]["reason"]
            terminal_event["artifact"] = copy.deepcopy(result["authority"])
            result["trace"].append(terminal_event)
        with state.lock:
            row = state.v2_runs[run_id]
            row["status"] = result["status"]
            row["active_stage"] = result["active_stage"]
            row["events"] = copy.deepcopy(result["trace"])
            row["result"] = result
            row["completed_at"] = time.time()
    except Exception as exc:  # noqa: BLE001 - failure is safely exposed to polling clients
        traceback.print_exc(file=sys.stderr)
        with state.lock:
            row = state.v2_runs[run_id]
            row["status"] = "failed"
            row["error"] = str(exc)
            row["completed_at"] = time.time()


def h_v2_get_run(state: AppState, run_id: str) -> dict[str, Any]:
    with state.lock:
        row = state.v2_runs.get(run_id)
        if row is None:
            raise NotFound(f"unknown run_id: {run_id}")
        return copy.deepcopy(row)


def h_v2_review(state: AppState, run_id: str, body: dict[str, Any]) -> dict[str, Any]:
    allowed_keys = {"action", "reason", "draft"}
    unknown_keys = sorted(set(body) - allowed_keys)
    if unknown_keys:
        raise BadRequest(f"unsupported review field(s): {unknown_keys}")
    action = body.get("action")
    if action not in {"approve", "reject", "edit"}:
        raise BadRequest("review action must be approve, reject, or edit")
    with state.lock:
        row = state.v2_runs.get(run_id)
        if row is None:
            raise NotFound(f"unknown run_id: {run_id}")
        result = copy.deepcopy(row.get("result"))
    if result is None:
        raise BadRequest("the run has not completed generation")

    reason = str(body.get("reason") or "").strip() or None
    if reason is not None and len(reason) > 500:
        raise BadRequest("review reason must not exceed 500 characters")
    draft_text = body.get("draft")
    if draft_text is not None:
        if not isinstance(draft_text, str) or not draft_text.strip():
            raise BadRequest("draft must be a non-empty string")
        if len(draft_text) > 12_000:
            raise BadRequest("draft must not exceed 12000 characters")
        inline_ids = set(re.findall(r"\[([A-Z0-9][A-Z0-9_.-]+)\]", draft_text))
        claims = {item["source_id"]: item["claim"] for item in result["draft"]["citations"]}
        result["draft"] = {
            **result["draft"],
            "text": draft_text.strip(),
            "citations": [
                {
                    "source_id": source_id,
                    "claim": claims.get(source_id, "Human-reviewed grounded claim"),
                }
                for source_id in sorted(inline_ids)
            ],
        }
        result["verification"] = verify_draft(
            result["request"],
            result["classification"],
            result["evidence"],
            result["decisions"],
            result["calculations"],
            result["authority"],
            result["draft"],
            result["verification"].get("repair_count", 0),
        )
        if not result["verification"]["passed"]:
            raise BadRequest(
                "edited draft failed verification: " + "; ".join(result["verification"]["errors"])
            )
        result["review"]["edited_draft"] = draft_text.strip()

    if action == "reject":
        result["status"] = "rejected"
        result["active_stage"] = "complete"
        result["authority"] = {
            **result["authority"],
            "state": "rejected",
            "can_send": False,
        }
    elif action == "approve":
        if not result["verification"].get("passed"):
            raise BadRequest("a draft that failed verification cannot be approved")
        result["status"] = "completed"
        result["active_stage"] = "complete"
        result["authority"] = {
            **result["authority"],
            "state": "approved",
            "can_send": True,
        }
    else:
        result["status"] = "awaiting_review"
        result["active_stage"] = "approval"
        result["authority"] = {
            **result["authority"],
            "requires_human": True,
            "state": "awaiting_review",
            "can_send": False,
            "reason": result["authority"]["reason"] + "; a human-edited draft requires approval",
        }

    result["review"].update(
        {"state": result["authority"]["state"], "action": action, "reason": reason}
    )
    case_id = result["request"]["case_id"]
    result["evaluation"] = state.evaluator.score(case_id, result)
    result["trace"].append(
        {
            "sequence": len(result["trace"]) + 1,
            "stage": "approval",
            "status": result["authority"]["state"],
            "summary": f"Human review action: {action}",
            "elapsed_ms": result.get("elapsed_ms", 0),
        }
    )
    with state.lock:
        row = state.v2_runs[run_id]
        row["status"] = result["status"]
        row["active_stage"] = result["active_stage"]
        row["events"] = copy.deepcopy(result["trace"])
        row["result"] = result
    return result


def h_get_knowledge(state: AppState) -> list[dict[str, Any]]:
    return knowledge_snapshot(state.documents)


def h_get_records(state: AppState) -> list[dict[str, Any]]:
    return record_snapshot(state.store)


class DemoHTTPServer(ThreadingHTTPServer):
    daemon_threads = True


class Handler(BaseHTTPRequestHandler):
    state: AppState
    protocol_version = "HTTP/1.1"
    server_version = "NRI-Demo"
    sys_version = ""

    def _common_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
            "font-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; "
            "base-uri 'none'; form-action 'self'",
        )

    def _send_json(self, status: int, payload: Any) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._common_headers()
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _send_file(self, path: Path, content_type: str) -> None:
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self._common_headers()
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def _send_unauthorized(self) -> None:
        body = b'{"error":"authentication required"}'
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="NRI private demo", charset="UTF-8"')
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._common_headers()
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _is_authorized(self) -> bool:
        return verify_basic_auth(
            Handler.state.settings,
            self.headers.get("Authorization", ""),
        )

    def _read_raw_body(self) -> bytes:
        try:
            length = validate_content_length(
                self.headers.get("Content-Length"),
                Handler.state.settings.max_body_bytes,
            )
        except PayloadTooLarge:
            self.close_connection = True
            raise
        return self.rfile.read(length) if length else b""

    def _parse_json_body(self, raw: bytes) -> dict[str, Any]:
        if raw and not self.headers.get("Content-Type", "").casefold().startswith(
            "application/json"
        ):
            raise UnsupportedMediaType("Content-Type must be application/json")
        if not raw.strip():
            return {}
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BadRequest("invalid JSON body") from exc
        if not isinstance(parsed, dict):
            raise BadRequest("request body must be a JSON object")
        return parsed

    def _serve_static(self, relative_name: str) -> bool:
        candidate = (ROOT / relative_name).resolve()
        try:
            candidate.relative_to(ROOT)
        except ValueError:
            return False
        if not candidate.is_file():
            return False
        guessed, _ = mimetypes.guess_type(candidate.name)
        content_type = guessed or "application/octet-stream"
        if candidate.suffix.casefold() in STATIC_TEXT_CHARSET_TYPES:
            content_type = f"{content_type}; charset=utf-8"
        self._send_file(candidate, content_type)
        return True

    def _dispatch(self, method: str) -> None:
        path = urlparse(self.path).path
        if path != "/healthz" and not self._is_authorized():
            self.close_connection = True
            self._send_unauthorized()
            return
        try:
            body_bytes = self._read_raw_body()
            result = self._route(method, path, body_bytes)
            if result is not None:
                status, payload = result
                self._send_json(status, payload)
        except ApiError as exc:
            self._send_json(exc.status, {"error": exc.message})
        except Exception:  # noqa: BLE001 - unexpected details stay in server logs
            traceback.print_exc(file=sys.stderr)
            self._send_json(500, {"error": "internal server error"})

    def _route(self, method: str, path: str, body_bytes: bytes) -> tuple[int, Any] | None:
        state = Handler.state
        if method in {"GET", "HEAD"} and path == "/healthz":
            return 200, {"status": "ok"}
        if method in {"GET", "HEAD"} and path in {"/", "/index.html"}:
            if self._serve_static("index.html"):
                return None
            raise NotFound("index.html not found")
        if method == "GET" and path == "/api/health":
            return 200, h_health(state)
        if method == "GET" and path == "/api/v2/cases":
            return 200, h_v2_cases(state)
        if method == "POST" and path == "/api/v2/runs":
            if not state.rate_limiter.allow(self.client_address[0]):
                raise TooManyRequests("run limit reached; try again later")
            return 202, h_v2_start_run(state, self._parse_json_body(body_bytes))
        review_match = V2_REVIEW_RE.fullmatch(path)
        if method == "POST" and review_match:
            return 200, h_v2_review(
                state,
                review_match.group(1),
                self._parse_json_body(body_bytes),
            )
        run_match = V2_RUN_ID_RE.fullmatch(path)
        if method == "GET" and run_match:
            return 200, h_v2_get_run(state, run_match.group(1))
        if method == "GET" and path == "/api/knowledge":
            return 200, h_get_knowledge(state)
        if method == "GET" and path == "/api/records":
            return 200, h_get_records(state)
        if method in {"GET", "HEAD"} and not path.startswith("/api/"):
            relative_name = path.lstrip("/")
            suffix = Path(relative_name).suffix.casefold()
            if (
                relative_name
                and suffix in STATIC_ASSET_EXTENSIONS
                and self._serve_static(relative_name)
            ):
                return None
        raise NotFound(f"no such route: {method} {path}")

    def do_GET(self) -> None:
        self._dispatch("GET")

    def do_HEAD(self) -> None:
        self._dispatch("HEAD")

    def do_POST(self) -> None:
        self._dispatch("POST")

    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A003
        sys.stderr.write(f"[nri-demo] {self.client_address[0]} - {fmt % args}\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="NRI Customer Service Agent Demo")
    parser.add_argument("--host", default=os.environ.get("NRI_HOST", DEFAULT_HOST))
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", DEFAULT_PORT)))
    args = parser.parse_args(argv)

    try:
        settings = Settings.from_environment(args.host, args.port)
    except ValueError as exc:
        parser.error(str(exc))
    state = AppState(settings=settings)
    Handler.state = state
    server = DemoHTTPServer((settings.host, settings.port), Handler)
    print(
        f"NRI demo listening on http://{settings.host}:{settings.port}/ "
        f"(auth={'required' if settings.auth_required else 'disabled'})",
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        state.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
