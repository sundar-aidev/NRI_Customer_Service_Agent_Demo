"""Convert classified needs into typed K searches and T tool calls."""

from __future__ import annotations

from typing import Any


KNOWLEDGE_NEEDS: dict[str, list[dict[str, Any]]] = {
    "warranty_terms": [
        {
            "family": "defects_warranties",
            "query": "warranty duration product category normal use misuse",
            "top_k": 1,
        },
    ],
    "return_eligibility": [
        {
            "family": "returns_refunds",
            "query": "general return eligibility window delivery date non-sale",
            "top_k": 1,
        },
    ],
    "partial_refund": [
        {
            "family": "returns_refunds",
            "query": "partial return refund coupon allocation shipping",
            "top_k": 1,
        },
    ],
    "coupon_proration": [
        {
            "family": "returns_refunds",
            "query": "coupon proration allocation line value partial refund",
            "top_k": 1,
        },
    ],
    "defect_return": [
        {
            "family": "returns_refunds",
            "query": "defective sale item return eligibility delivery",
            "top_k": 1,
        },
    ],
    "remedy_ownership": [
        {
            "family": "marketplace",
            "query": "marketplace seller fulfilment responsibility sale exclusion",
            "top_k": 1,
        },
        {
            "family": "open_decisions",
            "query": "precedence conflict seller policy defect return",
            "top_k": 1,
        },
    ],
    "replacement": [
        {
            "family": "fulfilment_remedies",
            "query": "zero stock replacement reship alternative refund",
            "top_k": 1,
        },
    ],
    "refund_composition": [
        {
            "family": "returns_refunds",
            "query": "refund composition coupon loyalty points expiry shipping",
            "top_k": 2,
        },
    ],
    "goodwill_compensation": [
        {
            "family": "goodwill",
            "query": "goodwill compensation coupon rolling cap approval",
            "top_k": 1,
        },
    ],
}

TRANSACTION_NEEDS: dict[str, tuple[str, ...]] = {
    "stock_availability": ("inventory",),
    "return_eligibility": ("order",),
    "partial_refund": ("order", "payment_allocation"),
    "coupon_proration": ("order", "payment_allocation"),
    "defect_return": ("order",),
    "remedy_ownership": ("order",),
    "replacement": ("order", "inventory"),
    "refund_composition": ("order", "payment_allocation", "loyalty_ledger"),
    "goodwill_compensation": ("compensation_history",),
}


def all_intents(classification: dict[str, Any]) -> list[str]:
    return [classification["primary_intent"], *classification.get("secondary_intents", [])]


def plan_retrieval(classification: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
    intents = all_intents(classification)
    knowledge_requests: list[dict[str, Any]] = []
    seen_k: set[tuple[str, str]] = set()
    for intent in intents:
        for need in KNOWLEDGE_NEEDS.get(intent, []):
            key = (need["family"], need["query"])
            if key not in seen_k:
                seen_k.add(key)
                knowledge_requests.append({**need, "supports": [intent]})

    transaction_tools: list[str] = []
    for intent in intents:
        for tool in TRANSACTION_NEEDS.get(intent, ()):
            if tool not in transaction_tools:
                transaction_tools.append(tool)
    # Preserve any valid model-requested lookup that the intent map did not add.
    for tool in classification.get("lookup_needs", []):
        if tool not in transaction_tools:
            transaction_tools.append(tool)

    context = request.get("conversation_context") or {}
    return {
        "knowledge_requests": knowledge_requests,
        "transaction_requests": [
            {
                "tool": tool,
                "arguments": {
                    "customer_id": context.get("customer_id", ""),
                    "order_id": context.get("active_order_id", ""),
                    "region": context.get("region", "SG"),
                    "product_names": classification.get("entities", {}).get("product_names", []),
                },
                "supports": [
                    intent for intent in intents if tool in TRANSACTION_NEEDS.get(intent, ())
                ],
            }
            for tool in transaction_tools
        ],
    }
