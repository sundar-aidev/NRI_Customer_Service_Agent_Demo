"""Allow-listed, customer-scoped transactional adapters over demo fixtures."""

from __future__ import annotations

import datetime as dt
import re
from typing import Any


class TransactionAccessError(ValueError):
    """Raised when a requested record is outside the authenticated scope."""


SYSTEM_BY_TOOL = {
    "order": "OMS · orders",
    "inventory": "WMS · inventory",
    "payment_allocation": "Payments · order_tenders",
    "loyalty_ledger": "Loyalty · points_ledger",
    "compensation_history": "CRM · compensation_history",
}


def _tokens(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", value.casefold()))


def _authorized_order(store: dict[str, dict], order_id: str, customer_id: str) -> dict[str, Any]:
    record = store.get(order_id)
    if not record or record.get("type") != "order":
        raise TransactionAccessError("authorized active order was not found")
    if not customer_id:
        raise TransactionAccessError("customer identity is required for order access")
    if record.get("customer_id") != customer_id:
        raise TransactionAccessError("active order does not belong to the authenticated customer")
    return record


def _record(
    source_id: str,
    tool: str,
    fields: dict[str, Any],
    supports: list[str],
    access_scope: dict[str, str],
) -> dict[str, Any]:
    return {
        "source_id": source_id,
        "system": SYSTEM_BY_TOOL[tool],
        "tool": tool,
        "tools": [tool],
        "fields": fields,
        "freshness": "fixture-live",
        "retrieved_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "access_scope": access_scope,
        "supports": list(dict.fromkeys(supports)),
        "selection_state": "selected",
    }


def _merge_record(target: dict[str, dict[str, Any]], item: dict[str, Any]) -> None:
    existing = target.get(item["source_id"])
    if existing is None:
        target[item["source_id"]] = item
        return
    existing["fields"].update(item["fields"])
    existing["supports"] = list(dict.fromkeys(existing["supports"] + item["supports"]))
    existing["tools"] = list(dict.fromkeys(existing["tools"] + item["tools"]))


def _inventory_match(
    store: dict[str, dict], product_names: list[str], order: dict | None
) -> dict | None:
    if order and order.get("items"):
        sku = order["items"][0].get("sku")
        candidate = store.get(sku)
        if candidate and candidate.get("type") == "sku":
            return candidate
    query_tokens = (
        set().union(*(_tokens(name) for name in product_names)) if product_names else set()
    )
    ranked: list[tuple[int, str, dict]] = []
    for source_id, record in store.items():
        if record.get("type") != "sku":
            continue
        overlap = len(query_tokens & (_tokens(record.get("title", "")) | _tokens(source_id)))
        if overlap:
            ranked.append((overlap, source_id, record))
    ranked.sort(key=lambda row: (-row[0], row[1]))
    if len(ranked) == 1 or (ranked and (len(ranked) == 1 or ranked[0][0] > ranked[1][0])):
        return ranked[0][2]
    return None


def execute_transaction_plan(plan: dict[str, Any], store: dict[str, dict]) -> dict[str, Any]:
    selected: dict[str, dict[str, Any]] = {}
    unresolved: list[dict[str, Any]] = []
    calls: list[dict[str, Any]] = []
    requests = list(plan.get("transaction_requests", []))
    # Order first because inventory, payments, and ledger may depend on it.
    requests.sort(key=lambda req: 0 if req["tool"] == "order" else 1)
    active_order: dict[str, Any] | None = None

    for request in requests:
        tool = request["tool"]
        args = request.get("arguments", {})
        supports = list(request.get("supports", []))
        customer_id = str(args.get("customer_id") or "")
        order_id = str(args.get("order_id") or "")
        call = {"tool": tool, "arguments": dict(args), "supports": supports, "status": "started"}
        calls.append(call)
        try:
            if tool in {"order", "payment_allocation", "loyalty_ledger"} and order_id:
                active_order = _authorized_order(store, order_id, customer_id)

            if tool == "order":
                if not order_id:
                    raise TransactionAccessError("active order is required; no record was guessed")
                assert active_order is not None
                fields = {
                    key: active_order.get(key)
                    for key in (
                        "order_number",
                        "customer_id",
                        "status",
                        "ordered_days_ago",
                        "delivered_days_ago",
                        "sale",
                        "defect_reported",
                        "seller",
                        "fulfilled_by",
                        "currency",
                        "category",
                        "items",
                    )
                }
                _merge_record(
                    selected,
                    _record(
                        order_id,
                        tool,
                        fields,
                        supports,
                        {"customer_id": customer_id, "order_id": order_id},
                    ),
                )
            elif tool == "payment_allocation":
                if not order_id:
                    raise TransactionAccessError("active order is required for payment allocation")
                assert active_order is not None
                fields = {
                    "coupon_percent": int(active_order.get("coupon_percent", 0)),
                    "shipping_cents": int(active_order.get("shipping_cents", 0)),
                    "points_applied_cents": int(active_order.get("points_applied_cents", 0)),
                    "currency": active_order.get("currency", "SGD"),
                }
                _merge_record(
                    selected,
                    _record(
                        order_id,
                        tool,
                        fields,
                        supports,
                        {"customer_id": customer_id, "order_id": order_id},
                    ),
                )
            elif tool == "inventory":
                record = _inventory_match(
                    store, list(args.get("product_names") or []), active_order
                )
                if record is None:
                    raise TransactionAccessError("inventory item is missing or ambiguous")
                if record.get("freshness") == "stale":
                    raise TransactionAccessError("inventory record is stale")
                source_id = str(record["sku"])
                fields = {
                    "sku": record["sku"],
                    "title": record.get("title", ""),
                    "available": int(record.get("available", 0)),
                    "locations_checked": list(record.get("locations_checked", [])),
                    "restock_eta": record.get("restock_eta"),
                }
                _merge_record(
                    selected,
                    _record(
                        source_id,
                        tool,
                        fields,
                        supports,
                        {"region": str(args.get("region") or "SG")},
                    ),
                )
            elif tool == "loyalty_ledger":
                matches = [
                    (source_id, record)
                    for source_id, record in store.items()
                    if record.get("type") == "points_ledger"
                    and record.get("customer_id") == customer_id
                    and record.get("order_number") == order_id
                ]
                if len(matches) != 1:
                    raise TransactionAccessError("loyalty ledger is missing or ambiguous")
                source_id, ledger = matches[0]
                fields = {
                    "customer_id": customer_id,
                    "order_number": order_id,
                    "tranches": list(ledger.get("tranches", [])),
                }
                _merge_record(
                    selected,
                    _record(
                        source_id,
                        tool,
                        fields,
                        supports,
                        {"customer_id": customer_id, "order_id": order_id},
                    ),
                )
            elif tool == "compensation_history":
                if not customer_id:
                    raise TransactionAccessError(
                        "customer identity is required for compensation history"
                    )
                matches = [
                    (source_id, record)
                    for source_id, record in store.items()
                    if record.get("type") == "compensation_history"
                    and record.get("customer_id") == customer_id
                ]
                if len(matches) != 1:
                    raise TransactionAccessError("compensation history is missing or ambiguous")
                source_id, history = matches[0]
                fields = {
                    "customer_id": customer_id,
                    "compensations_last_90_days": int(history.get("compensations_last_90_days", 0)),
                    "fraud_flag": bool(history.get("fraud_flag", False)),
                    "grants": list(history.get("grants", [])),
                }
                _merge_record(
                    selected,
                    _record(
                        source_id,
                        tool,
                        fields,
                        supports,
                        {"customer_id": customer_id},
                    ),
                )
            else:
                raise TransactionAccessError(f"unsupported transaction tool: {tool}")
            call["status"] = "completed"
        except TransactionAccessError as exc:
            call["status"] = "blocked"
            call["error"] = str(exc)
            unresolved.append(
                {
                    "type": "transaction_unavailable",
                    "tool": tool,
                    "reason": str(exc),
                    "supports": supports,
                }
            )

    return {
        # Preserve typed-tool order: order, inventory, payment merge, ledger,
        # then customer history. This mirrors the decision dependency flow.
        "selected": list(selected.values()),
        "calls": calls,
        "unresolved": unresolved,
    }
