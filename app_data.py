"""Shared serialization for the demo's read-only knowledge and record stores."""

from __future__ import annotations

from typing import Any

from knowledge.retriever import Document, load_all
from records.resolver import load_store


def serialize_document(document: Document) -> dict[str, Any]:
    return {
        "id": document.id,
        "title": document.title,
        "kind": document.kind,
        "version": document.version,
        "effective_date": document.effective_date,
        "owner": document.owner,
        "status": document.status,
        "provenance": document.provenance,
        "provenance_note": document.provenance_note,
        "body": document.body,
        "params": dict(document.params),
        "edited": False,
        "gap_consequence": document.gap_consequence,
        "gap_escalation": document.gap_escalation,
        "gap_closure": document.gap_closure,
    }


def knowledge_snapshot(documents: dict[str, Document] | None = None) -> list[dict[str, Any]]:
    source = load_all() if documents is None else documents
    return [serialize_document(document) for document in source.values()]


def record_snapshot(store: dict[str, dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    source = load_store() if store is None else store
    return [{"id": record_id, **record} for record_id, record in source.items()]


def static_snapshot() -> dict[str, list[dict[str, Any]]]:
    """Fallback content used only before the live backend connects."""
    return {
        "knowledge": knowledge_snapshot(),
        "records": record_snapshot(),
    }
