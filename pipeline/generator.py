"""Grounded response generation and constrained one-shot repair."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .model_provider import JsonModelProvider
from .schemas import DRAFT_JSON_SCHEMA, validate_draft


ROOT = Path(__file__).resolve().parents[1]
RESPONSE_PROMPT = ROOT / "prompts" / "response_v1.md"
REPAIR_PROMPT = ROOT / "prompts" / "repair_v1.md"


def _packet(
    request: dict[str, Any],
    classification: dict[str, Any],
    evidence: dict[str, Any],
    decisions: list[dict[str, Any]],
    calculations: list[dict[str, Any]],
    authority: dict[str, Any],
) -> dict[str, Any]:
    return {
        "inquiry": {
            "query": request["query"],
            "channel": request.get("channel", "marketplace_chat"),
            "locale": request.get("locale", "en-SG"),
        },
        "classification": {
            key: classification[key]
            for key in (
                "primary_intent",
                "secondary_intents",
                "requirements",
                "risk_flags",
            )
        },
        "evidence": {
            "knowledge": [
                {
                    "source_id": item["source_id"],
                    "title": item["title"],
                    "status": item["status"],
                    "matched_passage": item["matched_passage"],
                    "params": item.get("params", {}),
                    "supports": item.get("supports", []),
                }
                for item in evidence.get("knowledge", [])
            ],
            "transactions": [
                {
                    "source_id": item["source_id"],
                    "system": item["system"],
                    "fields": item["fields"],
                    "freshness": item["freshness"],
                    "supports": item.get("supports", []),
                }
                for item in evidence.get("transactions", [])
            ],
            "verified_context": list(evidence.get("context", [])),
            "policy_gaps": list(evidence.get("policy_gaps", [])),
            "unresolved": list(evidence.get("unresolved", [])),
        },
        "deterministic_decisions": decisions,
        "deterministic_calculations": calculations,
        "authority": authority,
    }


def generate_draft(
    request: dict[str, Any],
    classification: dict[str, Any],
    evidence: dict[str, Any],
    decisions: list[dict[str, Any]],
    calculations: list[dict[str, Any]],
    authority: dict[str, Any],
    provider: JsonModelProvider,
    *,
    previous: dict[str, Any] | None = None,
    verification_errors: list[str] | None = None,
) -> dict[str, Any]:
    packet = _packet(request, classification, evidence, decisions, calculations, authority)
    prompt = RESPONSE_PROMPT.read_text(encoding="utf-8")
    purpose = "response_generation"
    if previous is not None:
        purpose = "response_repair"
        prompt += "\n\n" + REPAIR_PROMPT.read_text(encoding="utf-8")
        packet["previous_draft"] = previous
        packet["verification_errors"] = list(verification_errors or [])
    raw = provider.generate_json(
        purpose,
        prompt + "\n\nFROZEN RUN PACKET\n" + json.dumps(packet, ensure_ascii=False, indent=2),
        DRAFT_JSON_SCHEMA,
    )
    draft = validate_draft(raw)
    # Stable citation order and no duplicate metadata rows.
    citations: dict[str, dict[str, str]] = {}
    for citation in draft["citations"]:
        citations.setdefault(citation["source_id"], citation)
    draft["citations"] = list(citations.values())
    return draft
