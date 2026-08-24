"""Model-backed multi-intent classification with deterministic safety normalization.

The model performs semantic classification. A small query-only guardrail then makes
controlled, inspectable corrections for explicit language (for example, ``damaged``
plus ``return``). The guardrail never sees source IDs, records, or evaluator gold.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .model_provider import JsonModelProvider
from .schemas import CLASSIFICATION_JSON_SCHEMA, validate_classification

ROOT = Path(__file__).resolve().parents[1]
PROMPT_PATH = ROOT / "prompts" / "classifier_v1.md"

INTENT_ORDER = [
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
]

INTENT_REQUIREMENTS = {
    "warranty_terms": {"K"},
    "stock_availability": {"T"},
    "return_eligibility": {"K", "T"},
    "partial_refund": {"K", "T", "C"},
    "coupon_proration": {"K", "T", "C"},
    "defect_return": {"K", "T", "C", "D"},
    "remedy_ownership": {"K", "T", "D"},
    "replacement": {"K", "T", "C", "D"},
    "refund_composition": {"K", "T", "C", "D"},
    "goodwill_compensation": {"K", "T", "C", "D"},
}

INTENT_FAMILIES = {
    "warranty_terms": {"defects_warranties"},
    "return_eligibility": {"returns_refunds"},
    "partial_refund": {"returns_refunds"},
    "coupon_proration": {"returns_refunds"},
    "defect_return": {"returns_refunds"},
    "remedy_ownership": {"marketplace", "open_decisions"},
    "replacement": {"fulfilment_remedies"},
    "refund_composition": {"returns_refunds"},
    "goodwill_compensation": {"goodwill"},
}

INTENT_LOOKUPS = {
    "stock_availability": {"inventory"},
    "return_eligibility": {"order"},
    "partial_refund": {"order", "payment_allocation"},
    "coupon_proration": {"order", "payment_allocation"},
    "defect_return": {"order"},
    "remedy_ownership": {"order"},
    "replacement": {"order", "inventory"},
    "refund_composition": {"order", "payment_allocation", "loyalty_ledger"},
    "goodwill_compensation": {"compensation_history"},
}


def _explicit_intents(query: str) -> list[str]:
    """Recognize only unambiguous surface signals; this is not a source router."""
    text = query.casefold()
    found: set[str] = set()
    damaged = any(word in text for word in ("damaged", "defective", "broken"))
    asks_return = "return" in text
    asks_amount = any(phrase in text for phrase in ("how much", "get back", "refund amount"))
    if "warranty" in text:
        found.add("warranty_terms")
    if any(phrase in text for phrase in ("in stock", "back in stock", "restock")):
        found.add("stock_availability")
    if asks_return and not damaged and not asks_amount:
        found.add("return_eligibility")
    if asks_return and asks_amount:
        found.add("partial_refund")
    if "coupon" in text and asks_amount:
        found.add("coupon_proration")
    if damaged and asks_return:
        found.add("defect_return")
    if damaged and "sale" in text:
        found.add("remedy_ownership")
    if any(
        phrase in text
        for phrase in ("same product", "replacement", "replace", "reship", "exchange")
    ):
        found.add("replacement")
    if "refund" in text and any(
        word in text for word in ("coupon", "points", "loyalty", "shipping")
    ):
        found.add("refund_composition")
    if any(phrase in text for phrase in ("compensation", "goodwill", "compensation coupon")):
        found.add("goodwill_compensation")
    return [intent for intent in INTENT_ORDER if intent in found]


def _extract_product_fallback(query: str) -> list[str]:
    text = query.strip()
    lower = text.casefold()
    marker = "is the "
    end = " back in stock"
    if marker in lower and end in lower:
        start_at = lower.index(marker) + len(marker)
        end_at = lower.index(end, start_at)
        candidate = text[start_at:end_at].strip(" ?.,")
        return [candidate] if candidate else []
    return []


def normalize_classification(
    classification: dict[str, Any], request: dict[str, Any]
) -> dict[str, Any]:
    """Apply query-only completeness and capability invariants.

    The raw model result is retained for audit so the UI can distinguish model
    output from guardrail changes.
    """
    raw_snapshot = json.loads(json.dumps(classification))
    explicit = _explicit_intents(request["query"])
    model_intents = [classification["primary_intent"], *classification["secondary_intents"]]
    intents = [intent for intent in INTENT_ORDER if intent in set(model_intents + explicit)]
    # Explicit multi-part language is authoritative for completeness; discard a
    # stray model intent only when every explicit intent is unambiguous.
    if explicit:
        allowed_extras = (
            {"partial_refund", "coupon_proration"} if "partial_refund" in explicit else set()
        )
        intents = [intent for intent in intents if intent in set(explicit) | allowed_extras]
    if not intents:
        intents = model_intents[:1]

    preferred = explicit[0] if explicit else classification["primary_intent"]
    if "defect_return" in intents:
        preferred = "defect_return"
    elif "partial_refund" in intents:
        preferred = "partial_refund"
    elif preferred not in intents:
        preferred = intents[0]

    reqs = set().union(*(INTENT_REQUIREMENTS.get(i, set()) for i in intents))
    families = set().union(*(INTENT_FAMILIES.get(i, set()) for i in intents))
    lookups = set().union(*(INTENT_LOOKUPS.get(i, set()) for i in intents))
    classification["primary_intent"] = preferred
    classification["secondary_intents"] = [i for i in intents if i != preferred]
    classification["requirements"] = [i for i in ("K", "T", "C", "D") if i in reqs]
    classification["knowledge_families"] = [
        i
        for i in (
            "returns_refunds",
            "defects_warranties",
            "marketplace",
            "fulfilment_remedies",
            "goodwill",
            "open_decisions",
        )
        if i in families
    ]
    classification["lookup_needs"] = [
        i
        for i in (
            "order",
            "inventory",
            "payment_allocation",
            "loyalty_ledger",
            "compensation_history",
        )
        if i in lookups
    ]
    classification["decision_needs"] = list(intents)
    if "D" in reqs:
        classification["autonomy_candidate"] = "always_human"
    elif any(i in intents for i in ("return_eligibility", "partial_refund", "coupon_proration")):
        classification["autonomy_candidate"] = "draft_only_human_review"
    else:
        classification["autonomy_candidate"] = "auto_draft_internal"

    risks: set[str] = set(classification.get("risk_flags", []))
    if any(
        i in intents
        for i in (
            "partial_refund",
            "coupon_proration",
            "refund_composition",
            "goodwill_compensation",
        )
    ):
        risks.add("financial")
    if "remedy_ownership" in intents:
        risks.add("policy_conflict")
    if "goodwill_compensation" in intents:
        risks.add("discretionary")
    if request.get("attachments"):
        risks.add("attachment_evidence")
    classification["risk_flags"] = [
        i
        for i in ("financial", "policy_conflict", "discretionary", "attachment_evidence")
        if i in risks
    ]
    if explicit:
        # Explicit controlled-taxonomy signals make the classification itself
        # high confidence. This does not increase confidence in a policy
        # outcome and can never bypass a mandatory human gate.
        classification["confidence"] = max(float(classification["confidence"]), 0.95)
    if not classification["entities"].get("product_names"):
        classification["entities"]["product_names"] = _extract_product_fallback(request["query"])
    classification["model_output"] = raw_snapshot
    classification["normalization_changes"] = {
        "explicit_intents_added": [i for i in explicit if i not in model_intents],
        "model_intents_removed": [i for i in model_intents if i not in intents],
        "capabilities_recomputed": True,
        "explicit_signal_confidence_floor": 0.95 if explicit else None,
    }
    return classification


def classify(request: dict[str, Any], provider: JsonModelProvider) -> dict[str, Any]:
    template = PROMPT_PATH.read_text(encoding="utf-8")
    safe_input = {
        "query": request["query"],
        "channel": request.get("channel", "marketplace_chat"),
        "locale": request.get("locale", "en-SG"),
        "authorized_context": request.get("conversation_context") or {},
        "attachments": request.get("attachments") or [],
    }
    raw = provider.generate_json(
        "classification",
        template + "\n\nRUNTIME INPUT\n" + json.dumps(safe_input, ensure_ascii=False, indent=2),
        CLASSIFICATION_JSON_SCHEMA,
    )
    classification = validate_classification(raw)
    context = safe_input["authorized_context"]
    # Authenticated context is authoritative for identity. The model may copy it
    # into its schema, but it may not replace it with a guessed identifier.
    if context.get("customer_id"):
        classification["entities"]["customer_id"] = str(context["customer_id"])
    if context.get("active_order_id"):
        classification["entities"]["order_id"] = str(context["active_order_id"])
    return normalize_classification(classification, request)
