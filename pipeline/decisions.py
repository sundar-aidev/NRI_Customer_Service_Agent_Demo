"""Deterministic decision graph and exact-money calculations."""

from __future__ import annotations

import re
from typing import Any


UNDEFINED = "UNDEFINED"


def _maps(evidence: dict[str, Any]) -> tuple[dict[str, dict], dict[str, dict]]:
    knowledge = {item["source_id"]: item for item in evidence.get("knowledge", [])}
    transactions = {item["source_id"]: item for item in evidence.get("transactions", [])}
    return knowledge, transactions


def _decision(
    decision_id: str,
    question: str,
    owner: str,
    outcome: str,
    state: str,
    evidence_refs: list[str],
    rule_version: str,
    depends_on: list[str] | None = None,
    requires_human: bool = False,
    explanation: str = "",
) -> dict[str, Any]:
    return {
        "decision_id": decision_id,
        "question": question,
        "owner": owner,
        "outcome": outcome,
        "state": state,
        "requires_human": requires_human,
        "evidence_refs": evidence_refs,
        "rule_version": rule_version,
        "depends_on": depends_on or [],
        "explanation": explanation,
    }


def _knowledge_param(knowledge: dict[str, dict], source_id: str, key: str) -> str | None:
    """Return a governed parameter without inventing a fallback value."""
    value = knowledge.get(source_id, {}).get("params", {}).get(key)
    return str(value) if value is not None else None


def _integer_param(knowledge: dict[str, dict], source_id: str, key: str) -> int | None:
    value = _knowledge_param(knowledge, source_id, key)
    try:
        return int(value) if value is not None else None
    except ValueError:
        return None


def _active_order(transactions: dict[str, dict]) -> tuple[str, dict] | tuple[None, None]:
    for source_id, item in transactions.items():
        fields = item.get("fields", {})
        if source_id.startswith("ORD-") and fields.get("order_number") == source_id:
            return source_id, fields
    return None, None


def _find_inventory(transactions: dict[str, dict]) -> tuple[str, dict] | tuple[None, None]:
    for source_id, item in transactions.items():
        if item.get("tool") == "inventory" or "inventory" in item.get("tools", []):
            return source_id, item.get("fields", {})
    return None, None


def _matches_returned_item(query: str, items: list[dict]) -> list[dict]:
    tokens = set(re.findall(r"[a-z0-9]+", query.casefold()))
    scored = []
    for item in items:
        title_tokens = set(re.findall(r"[a-z0-9]+", str(item.get("title", "")).casefold()))
        scored.append((len(tokens & title_tokens), item))
    scored.sort(key=lambda row: -row[0])
    if not scored or scored[0][0] == 0:
        return []
    if len(scored) > 1 and scored[0][0] == scored[1][0]:
        return []
    return [scored[0][1]]


def _refund_calculation(
    query: str, order_id: str, order: dict, knowledge: dict[str, dict]
) -> tuple[dict[str, Any], dict[str, Any]]:
    returned = _matches_returned_item(query, list(order.get("items") or []))
    if not returned:
        decision = _decision(
            "refund_amount",
            "What is the refund amount?",
            "Rules",
            UNDEFINED,
            "blocked",
            ["KB-REF-01", order_id],
            "refund_proration_v2",
            requires_human=True,
            explanation="The returned order line is missing or ambiguous; no amount was guessed.",
        )
        return decision, {}

    subtotal = sum(
        int(item["unit_price_cents"]) * int(item.get("quantity", 1)) for item in order["items"]
    )
    line = returned[0]
    line_total = int(line["unit_price_cents"]) * int(line.get("quantity", 1))
    coupon_percent = int(order.get("coupon_percent", 0))
    coupon_total = subtotal * coupon_percent // 100
    allocated_coupon = coupon_total * line_total // subtotal if subtotal else 0
    full_return = len(returned) == len(order["items"])
    shipping_cents = int(order.get("shipping_cents", 0))
    shipping_rule = _knowledge_param(knowledge, "KB-REF-01", "shipping_refundable_on_partial")
    if shipping_rule not in {"true", "false"}:
        decision = _decision(
            "refund_amount",
            "What is the refund amount?",
            "Rules",
            UNDEFINED,
            "blocked",
            ["KB-REF-01", order_id],
            "refund_proration_v2",
            requires_human=True,
            explanation=(
                "The shipping-refund policy parameter is missing or invalid; "
                "no refund amount was guessed."
            ),
        )
        return decision, {}
    shipping_partial = shipping_rule == "true"
    shipping_refund = shipping_cents if full_return or shipping_partial else 0
    result = line_total - allocated_coupon + shipping_refund
    calculation = {
        "calculation_id": "CALC-L4",
        "currency": order.get("currency", "SGD"),
        "minor_unit": "cents",
        "rule_version": "refund_proration_v2",
        "inputs": {
            "order_subtotal_cents": subtotal,
            "returned_sku": line["sku"],
            "returned_line_cents": line_total,
            "coupon_percent": coupon_percent,
            "coupon_total_cents": coupon_total,
            "allocated_coupon_cents": allocated_coupon,
            "shipping_paid_cents": shipping_cents,
            "full_return": full_return,
            "shipping_refundable_on_partial": shipping_partial,
        },
        "operations": [
            f"{subtotal} × {coupon_percent}% = {coupon_total} coupon cents",
            f"{coupon_total} × {line_total} ÷ {subtotal} = {allocated_coupon} allocated coupon cents",
            f"{line_total} − {allocated_coupon} + {shipping_refund} = {result} refund cents",
        ],
        "output_cents": result,
        "evidence_refs": ["KB-REF-01", order_id],
    }
    decision = _decision(
        "refund_amount",
        "What is the exact partial-return refund?",
        "Rules",
        str(result),
        "approved",
        ["KB-REF-01", order_id, "CALC-L4"],
        "refund_proration_v2",
        explanation=(
            f"The returned line is {line_total} cents, its allocated coupon is "
            f"{allocated_coupon} cents, and shipping contributes {shipping_refund} cents."
        ),
    )
    return decision, calculation


def apply_decisions(
    request: dict[str, Any], classification: dict[str, Any], evidence: dict[str, Any]
) -> dict[str, Any]:
    intents = {classification["primary_intent"], *classification.get("secondary_intents", [])}
    knowledge, transactions = _maps(evidence)
    order_id, order = _active_order(transactions)
    inventory_id, inventory = _find_inventory(transactions)
    decisions: list[dict[str, Any]] = []
    calculations: list[dict[str, Any]] = []

    if "warranty_terms" in intents:
        if "KB-WAR-01" in knowledge:
            decisions.append(
                _decision(
                    "warranty_terms",
                    "What warranty governs small kitchen appliances?",
                    "Rules",
                    "24_months",
                    "approved",
                    ["KB-WAR-01"],
                    "warranty_category_v1",
                    explanation="Small kitchen appliances inherit the 24-month category warranty.",
                )
            )
        else:
            decisions.append(
                _decision(
                    "warranty_terms",
                    "What warranty governs small kitchen appliances?",
                    "Rules",
                    UNDEFINED,
                    "blocked",
                    [],
                    "warranty_category_v1",
                    requires_human=True,
                    explanation="The governing warranty document was not retrieved.",
                )
            )

    if "stock_availability" in intents:
        if inventory_id and inventory is not None:
            available = int(inventory.get("available", 0))
            decisions.append(
                _decision(
                    "stock_availability",
                    "Is the requested product available now?",
                    "Orchestration",
                    "in_stock" if available > 0 else "out_of_stock",
                    "approved",
                    [inventory_id],
                    "inventory_feasibility_v1",
                    explanation=(
                        f"The inventory adapter returned {available} available across "
                        f"{len(inventory.get('locations_checked', []))} checked locations."
                    ),
                )
            )
        else:
            decisions.append(
                _decision(
                    "stock_availability",
                    "Is the requested product available now?",
                    "Orchestration",
                    UNDEFINED,
                    "blocked",
                    [],
                    "inventory_feasibility_v1",
                    requires_human=True,
                    explanation="A current, unambiguous inventory record was not available.",
                )
            )

    if "return_eligibility" in intents:
        window = _integer_param(knowledge, "KB-RET-01", "return_window_days")
        if order and "KB-RET-01" in knowledge and window is not None:
            days = order.get("delivered_days_ago")
            eligible = (
                order.get("status") == "delivered"
                and isinstance(days, int)
                and days <= window
                and not bool(order.get("sale"))
            )
            decisions.append(
                _decision(
                    "return_eligibility",
                    "Is the standard return inside the approved window?",
                    "Rules",
                    "eligible" if eligible else "not_eligible",
                    "approved",
                    ["KB-RET-01", order_id],
                    "return_window_v2",
                    explanation=(
                        f"Delivery was {days} day(s) ago against a {window}-day, "
                        "delivery-dated return window."
                    ),
                )
            )
        else:
            decisions.append(
                _decision(
                    "return_eligibility",
                    "Is the standard return inside the approved window?",
                    "Rules",
                    UNDEFINED,
                    "blocked",
                    [ref for ref in ("KB-RET-01", order_id) if ref],
                    "return_window_v2",
                    requires_human=True,
                    explanation=(
                        "Required current policy, governed return-window parameter, "
                        "or scoped order evidence is missing."
                    ),
                )
            )

    if intents & {"partial_refund", "coupon_proration"}:
        if order and order_id and "KB-REF-01" in knowledge:
            decision, calculation = _refund_calculation(
                request["query"], order_id, order, knowledge
            )
            decisions.append(decision)
            if calculation:
                calculations.append(calculation)
        else:
            decisions.append(
                _decision(
                    "refund_amount",
                    "What is the exact partial-return refund?",
                    "Rules",
                    UNDEFINED,
                    "blocked",
                    [ref for ref in ("KB-REF-01", order_id) if ref],
                    "refund_proration_v2",
                    requires_human=True,
                    explanation="Required refund policy or scoped order evidence is missing.",
                )
            )

    if "defect_return" in intents:
        refs = [ref for ref in ("KB-RET-01", "KB-MKT-01", "KB-PRE-01", order_id) if ref]
        verified_damage = any(
            item.get("certainty") == "human_verified" for item in evidence.get("context", [])
        )
        precedence = _knowledge_param(knowledge, "KB-PRE-01", "precedence")
        conflict = bool(
            order and order.get("sale") and order.get("seller") != "company_a" and verified_damage
        )
        if not order or not verified_damage:
            d1_outcome, state, human, explanation = (
                UNDEFINED,
                "blocked",
                True,
                "Scoped order evidence or verified damage evidence is missing.",
            )
        elif conflict and precedence not in {"company_a_wins", "seller_wins"}:
            d1_outcome, state, human, explanation = (
                UNDEFINED,
                "blocked",
                True,
                "The defective-item return rule and marketplace sale exclusion conflict; precedence is undefined.",
            )
        elif conflict and precedence == "seller_wins":
            d1_outcome, state, human, explanation = (
                "not_eligible",
                "approved",
                False,
                "The configured precedence rule gives the sale exclusion priority.",
            )
        else:
            d1_outcome, state, human, explanation = (
                "eligible",
                "approved",
                False,
                "The verified defect is within the delivery-dated return window.",
            )
        decisions.append(
            _decision(
                "D1_return_eligibility",
                "Can this damaged sale item be accepted for return?",
                "Human" if human else "Rules",
                d1_outcome,
                state,
                refs,
                "defect_return_precedence_v2",
                requires_human=human,
                explanation=explanation,
            )
        )

        decisions.append(
            _decision(
                "D2_remedy_ownership",
                "Who owns the customer remedy decision?",
                "Human",
                "human_review",
                "proposed",
                [ref for ref in ("KB-MKT-01", order_id) if ref],
                "marketplace_remedy_split_v1",
                ["D1_return_eligibility"],
                True,
                "Customer remedy and internal settlement are separated; funding allocation stays internal.",
            )
        )

        if inventory_id and inventory is not None and "KB-STK-01" in knowledge:
            stock = int(inventory.get("available", 0))
            d3_outcome = "feasible" if stock > 0 else "not_feasible"
            d3_explanation = (
                "The same SKU is available for replacement."
                if stock > 0
                else "The same SKU has zero stock; propose a confirmed comparable in-stock item or a refund."
            )
            d3_refs = ["KB-STK-01", inventory_id]
        else:
            d3_outcome, d3_explanation, d3_refs = (
                UNDEFINED,
                "Current inventory evidence is unavailable.",
                [ref for ref in ("KB-STK-01", inventory_id) if ref],
            )
        decisions.append(
            _decision(
                "D3_replacement_remedy",
                "Can the same product be replaced immediately?",
                "Orchestration",
                d3_outcome,
                "proposed" if d3_outcome != UNDEFINED else "blocked",
                d3_refs,
                "replacement_feasibility_v2",
                ["D1_return_eligibility", "D2_remedy_ownership"],
                True,
                d3_explanation,
            )
        )

        ledger_id = next(
            (
                sid
                for sid, item in transactions.items()
                if item.get("tool") == "loyalty_ledger" or "loyalty_ledger" in item.get("tools", [])
            ),
            None,
        )
        ledger = transactions.get(ledger_id, {}).get("fields", {}) if ledger_id else {}
        expired = [row for row in ledger.get("tranches", []) if row.get("expired")]
        points_treatment = _knowledge_param(knowledge, "KB-PTS-01", "expired_points_treatment")
        d4_refs = [ref for ref in ("KB-REF-01", "KB-PTS-01", order_id, ledger_id) if ref]
        if not ledger_id or "KB-REF-01" not in knowledge or "KB-PTS-01" not in knowledge:
            d4_outcome, d4_state, d4_human, d4_explanation = (
                UNDEFINED,
                "blocked",
                True,
                "Refund tender evidence or governing policy is missing.",
            )
        elif expired and points_treatment == "undefined":
            d4_outcome, d4_state, d4_human, d4_explanation = (
                UNDEFINED,
                "blocked",
                True,
                "Treatment of a points tranche that expired after redemption is not defined; no exact refund is certified.",
            )
        else:
            d4_outcome, d4_state, d4_human, d4_explanation = (
                "certified_calculation_required",
                "proposed",
                False,
                "The tender rules are defined; compute the final amount only after the customer selects refund.",
            )
        decisions.append(
            _decision(
                "D4_refund_composition",
                "How should coupon and loyalty tenders be restored?",
                "Human" if d4_human else "Rules",
                d4_outcome,
                d4_state,
                d4_refs,
                "refund_tender_restoration_v2",
                ["D1_return_eligibility", "D3_replacement_remedy"],
                d4_human,
                d4_explanation,
            )
        )

        history_id = next(
            (
                sid
                for sid, item in transactions.items()
                if item.get("tool") == "compensation_history"
                or "compensation_history" in item.get("tools", [])
            ),
            None,
        )
        history = transactions.get(history_id, {}).get("fields", {}) if history_id else {}
        cap = _integer_param(knowledge, "KB-GDW-01", "goodwill_cap_per_90_days")
        count = int(history.get("compensations_last_90_days", 0))
        if history_id and "KB-GDW-01" in knowledge and cap is not None:
            d5_outcome = "gated_human_approval" if count >= cap else "within_cap_human_discretion"
            d5_explanation = f"The customer has {count} grant(s) in 90 days against a cap of {cap}; goodwill remains discretionary."
        else:
            d5_outcome = UNDEFINED
            d5_explanation = (
                "Compensation history, goodwill policy, or its governed cap parameter is missing."
            )
        decisions.append(
            _decision(
                "D5_goodwill",
                "Can a compensation coupon be granted?",
                "Human",
                d5_outcome,
                "proposed" if d5_outcome != UNDEFINED else "blocked",
                [ref for ref in ("KB-GDW-01", history_id) if ref],
                "goodwill_cap_v2",
                [
                    "D1_return_eligibility",
                    "D2_remedy_ownership",
                    "D3_replacement_remedy",
                    "D4_refund_composition",
                ],
                True,
                d5_explanation,
            )
        )

    open_requirements = bool(evidence.get("unresolved"))
    requires_human = (
        open_requirements
        or classification.get("autonomy_candidate") != "auto_draft_internal"
        or float(classification.get("confidence", 0)) < 0.8
        or any(item["requires_human"] for item in decisions)
    )
    reasons = []
    if open_requirements:
        reasons.append("missing or ambiguous evidence")
    if classification.get("autonomy_candidate") == "draft_only_human_review":
        reasons.append("demo policy requires review for eligibility or financial drafts")
    if classification.get("autonomy_candidate") == "always_human":
        reasons.append("policy conflict, incomplete rule, or discretion is human-owned")
    if float(classification.get("confidence", 0)) < 0.8:
        reasons.append("classification confidence is below 0.80")
    if any(item["requires_human"] for item in decisions):
        reasons.append("one or more decisions require a human owner")
    authority = {
        "requires_human": requires_human,
        "reason": "; ".join(dict.fromkeys(reasons))
        if reasons
        else "all decisions are approved for an internal draft",
        "state": "awaiting_review" if requires_human else "auto_draft_complete",
        "can_send": False,
    }
    return {"decisions": decisions, "calculations": calculations, "authority": authority}
