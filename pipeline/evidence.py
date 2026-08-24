"""Normalize K, T, and verified attachment observations into a frozen bundle."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def normalize_evidence(
    request: dict[str, Any], knowledge: dict[str, Any], transactions: dict[str, Any]
) -> dict[str, Any]:
    context = []
    for attachment in request.get("attachments", []):
        context.append(
            {
                "source_id": str(attachment.get("id", "")),
                "type": "attachment_observation",
                "filename": str(attachment.get("filename", "")),
                "certainty": str(attachment.get("certainty", "provided")),
                "observation": str(attachment.get("observation", "")),
                "selection_state": "verified"
                if attachment.get("certainty") == "human_verified"
                else "provided",
            }
        )

    gaps = [
        {
            "source_id": item["source_id"],
            "status": item["status"],
            "owner": item["owner"],
            "supports": list(item.get("supports", [])),
        }
        for item in knowledge["selected"]
        if item["status"] in {"undefined", "incomplete"}
    ]
    conflicts = []
    selected_ids = {item["source_id"] for item in knowledge["selected"]}
    if {"KB-RET-01", "KB-MKT-01", "KB-PRE-01"}.issubset(selected_ids):
        conflicts.append(
            {
                "type": "policy_precedence",
                "sources": ["KB-RET-01", "KB-MKT-01", "KB-PRE-01"],
                "state": "unresolved",
            }
        )
    bundle: dict[str, Any] = {
        "knowledge": knowledge["selected"],
        "transactions": transactions["selected"],
        "context": context,
        "excluded_knowledge": knowledge["excluded"],
        "unresolved": [*knowledge["unresolved"], *transactions["unresolved"]],
        "policy_gaps": gaps,
        "conflicts": conflicts,
        "retrieval_audit": {
            "knowledge_queries": knowledge["queries"],
            "transaction_calls": transactions["calls"],
        },
    }
    digest_payload = json.dumps(bundle, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    bundle["snapshot_hash"] = hashlib.sha256(digest_payload.encode("utf-8")).hexdigest()[:20]
    return bundle


def evidence_source_ids(bundle: dict[str, Any]) -> set[str]:
    return {
        item["source_id"]
        for family in ("knowledge", "transactions", "context")
        for item in bundle.get(family, [])
        if item.get("source_id")
    }
