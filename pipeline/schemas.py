"""Controlled schemas and validation for model-backed pipeline stages."""

from __future__ import annotations

from typing import Any


INTENTS = (
    "warranty_terms",
    "stock_availability",
    "return_eligibility",
    "partial_refund",
    "coupon_proration",
    "defect_return",
    "remedy_ownership",
    "replacement",
    "refund_composition",
    "goodwill_compensation",
)

REQUIREMENT_ORDER = ("K", "T", "C", "D")
KNOWLEDGE_FAMILIES = (
    "returns_refunds",
    "defects_warranties",
    "marketplace",
    "fulfilment_remedies",
    "goodwill",
    "open_decisions",
)
LOOKUP_NEEDS = (
    "order",
    "inventory",
    "payment_allocation",
    "loyalty_ledger",
    "compensation_history",
)
AUTONOMY = ("auto_draft_internal", "draft_only_human_review", "always_human")
RISK_FLAGS = ("financial", "policy_conflict", "discretionary", "attachment_evidence")


class SchemaError(ValueError):
    """Raised when a model response violates a controlled runtime schema."""


CLASSIFICATION_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "primary_intent",
        "secondary_intents",
        "confidence",
        "requirements",
        "entities",
        "knowledge_families",
        "lookup_needs",
        "decision_needs",
        "autonomy_candidate",
        "risk_flags",
        "missing_information",
    ],
    "properties": {
        "primary_intent": {"type": "string", "enum": list(INTENTS)},
        "secondary_intents": {
            "type": "array",
            "items": {"type": "string", "enum": list(INTENTS)},
        },
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "requirements": {
            "type": "array",
            "items": {"type": "string", "enum": list(REQUIREMENT_ORDER)},
        },
        "entities": {
            "type": "object",
            "additionalProperties": False,
            "required": ["customer_id", "order_id", "product_names", "item_names"],
            "properties": {
                "customer_id": {"type": "string"},
                "order_id": {"type": "string"},
                "product_names": {"type": "array", "items": {"type": "string"}},
                "item_names": {"type": "array", "items": {"type": "string"}},
            },
        },
        "knowledge_families": {
            "type": "array",
            "items": {"type": "string", "enum": list(KNOWLEDGE_FAMILIES)},
        },
        "lookup_needs": {
            "type": "array",
            "items": {"type": "string", "enum": list(LOOKUP_NEEDS)},
        },
        "decision_needs": {
            "type": "array",
            "items": {"type": "string", "enum": list(INTENTS)},
        },
        "autonomy_candidate": {"type": "string", "enum": list(AUTONOMY)},
        "risk_flags": {
            "type": "array",
            "items": {"type": "string", "enum": list(RISK_FLAGS)},
        },
        "missing_information": {"type": "array", "items": {"type": "string"}},
    },
}


DRAFT_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["text", "citations", "answered_intents", "unanswered_intents"],
    "properties": {
        "text": {"type": "string", "minLength": 1},
        "citations": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["source_id", "claim"],
                "properties": {
                    "source_id": {"type": "string"},
                    "claim": {"type": "string"},
                },
            },
        },
        "answered_intents": {
            "type": "array",
            "items": {"type": "string", "enum": list(INTENTS)},
        },
        "unanswered_intents": {
            "type": "array",
            "items": {"type": "string", "enum": list(INTENTS)},
        },
    },
}


def _strings(value: Any, field: str, allowed: tuple[str, ...] | None = None) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise SchemaError(f"{field} must be an array of strings")
    if allowed is not None:
        invalid = sorted(set(value) - set(allowed))
        if invalid:
            raise SchemaError(f"{field} contains unsupported values: {invalid}")
    return list(dict.fromkeys(value))


def validate_classification(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SchemaError("classification must be an object")
    primary = value.get("primary_intent")
    if primary not in INTENTS:
        raise SchemaError(f"unsupported primary_intent: {primary!r}")
    secondary = _strings(value.get("secondary_intents"), "secondary_intents", INTENTS)
    secondary = [intent for intent in secondary if intent != primary]
    confidence = value.get("confidence")
    if not isinstance(confidence, (int, float)) or not 0 <= float(confidence) <= 1:
        raise SchemaError("confidence must be between 0 and 1")
    entities = value.get("entities")
    if not isinstance(entities, dict):
        raise SchemaError("entities must be an object")
    for key in ("customer_id", "order_id"):
        if not isinstance(entities.get(key), str):
            raise SchemaError(f"entities.{key} must be a string")
    product_names = _strings(entities.get("product_names"), "entities.product_names")
    item_names = _strings(entities.get("item_names"), "entities.item_names")

    requirements = _strings(value.get("requirements"), "requirements", REQUIREMENT_ORDER)
    requirements = [item for item in REQUIREMENT_ORDER if item in requirements]
    families = _strings(
        value.get("knowledge_families"),
        "knowledge_families",
        KNOWLEDGE_FAMILIES,
    )
    lookups = _strings(value.get("lookup_needs"), "lookup_needs", LOOKUP_NEEDS)
    decisions = _strings(value.get("decision_needs"), "decision_needs", INTENTS)
    autonomy = value.get("autonomy_candidate")
    if autonomy not in AUTONOMY:
        raise SchemaError(f"unsupported autonomy_candidate: {autonomy!r}")
    risks = _strings(value.get("risk_flags"), "risk_flags", RISK_FLAGS)
    missing = _strings(value.get("missing_information"), "missing_information")

    return {
        "primary_intent": primary,
        "secondary_intents": secondary,
        "confidence": round(float(confidence), 4),
        "requirements": requirements,
        "entities": {
            "customer_id": entities["customer_id"],
            "order_id": entities["order_id"],
            "product_names": product_names,
            "item_names": item_names,
        },
        "knowledge_families": families,
        "lookup_needs": lookups,
        "decision_needs": decisions,
        "autonomy_candidate": autonomy,
        "risk_flags": risks,
        "missing_information": missing,
    }


def validate_draft(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or not isinstance(value.get("text"), str):
        raise SchemaError("draft must be an object with text")
    citations = value.get("citations")
    if not isinstance(citations, list):
        raise SchemaError("draft.citations must be an array")
    normalized_citations = []
    for item in citations:
        if not isinstance(item, dict):
            raise SchemaError("each citation must be an object")
        source_id, claim = item.get("source_id"), item.get("claim")
        if not isinstance(source_id, str) or not isinstance(claim, str):
            raise SchemaError("citation source_id and claim must be strings")
        normalized_citations.append({"source_id": source_id, "claim": claim})
    answered = _strings(value.get("answered_intents"), "answered_intents", INTENTS)
    unanswered = _strings(value.get("unanswered_intents"), "unanswered_intents", INTENTS)
    return {
        "text": value["text"].strip(),
        "citations": normalized_citations,
        "answered_intents": answered,
        "unanswered_intents": unanswered,
    }
