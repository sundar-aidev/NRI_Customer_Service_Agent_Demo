"""Deterministic grounding, arithmetic, citation, and authority verifier."""

from __future__ import annotations

import re
from typing import Any

from .evidence import evidence_source_ids


CITATION_RE = re.compile(r"\[([A-Z0-9][A-Z0-9_.-]+)\]")


def _contains(text: str, *variants: str) -> bool:
    normalized = text.casefold().replace("‑", "-").replace("–", "-")
    return any(variant.casefold() in normalized for variant in variants)


def _require(errors: list[str], condition: bool, message: str) -> None:
    if not condition:
        errors.append(message)


def _cited(text_ids: set[str], *candidates: str | None) -> bool:
    return any(candidate in text_ids for candidate in candidates if candidate)


def verify_draft(
    request: dict[str, Any],
    classification: dict[str, Any],
    evidence: dict[str, Any],
    decisions: list[dict[str, Any]],
    calculations: list[dict[str, Any]],
    authority: dict[str, Any],
    draft: dict[str, Any],
    repair_count: int = 0,
) -> dict[str, Any]:
    errors: list[str] = []
    text = draft.get("text", "")
    lower = text.casefold()
    valid_sources = evidence_source_ids(evidence) | {
        item["calculation_id"] for item in calculations if item.get("calculation_id")
    }
    inline_ids = set(CITATION_RE.findall(text))
    metadata_ids = {item.get("source_id") for item in draft.get("citations", [])}
    unknown_inline = sorted(inline_ids - valid_sources)
    unknown_metadata = sorted(metadata_ids - valid_sources)
    missing_inline = sorted(metadata_ids - inline_ids)
    undocumented_inline = sorted(inline_ids - metadata_ids)
    if unknown_inline:
        errors.append(f"Inline citations are not in frozen evidence: {unknown_inline}")
    if unknown_metadata:
        errors.append(f"Citation metadata references unavailable sources: {unknown_metadata}")
    if missing_inline:
        errors.append(f"Citation metadata is not present inline: {missing_inline}")
    if undocumented_inline:
        errors.append(f"Inline citations lack citation metadata: {undocumented_inline}")
    if any(
        item.get("status") == "retired" and item["source_id"] in inline_ids
        for item in evidence.get("knowledge", [])
    ):
        errors.append("A retired policy was cited")

    intents = {classification["primary_intent"], *classification.get("secondary_intents", [])}
    decision_map = {item["decision_id"]: item for item in decisions}
    tx_ids = {item["source_id"] for item in evidence.get("transactions", [])}
    attachment_ids = {
        item["source_id"]
        for item in evidence.get("context", [])
        if item.get("certainty") == "human_verified"
    }
    order_id = next((source_id for source_id in tx_ids if source_id.startswith("ORD-")), None)
    inventory_id = next((source_id for source_id in tx_ids if source_id.startswith("SKU-")), None)
    ledger_id = next((source_id for source_id in tx_ids if source_id.startswith("PTS-")), None)
    history_id = next((source_id for source_id in tx_ids if source_id.startswith("HIST-")), None)

    if "warranty_terms" in intents:
        _require(
            errors, _contains(text, "24-month", "24 month"), "Warranty draft must state 24 months"
        )
        _require(
            errors, _contains(text, "normal use"), "Warranty draft must state normal-use coverage"
        )
        _require(
            errors, _contains(text, "misuse"), "Warranty draft must state the misuse exclusion"
        )
        _require(errors, "KB-WAR-01" in inline_ids, "Warranty facts must cite KB-WAR-01")

    if "stock_availability" in intents:
        outcome = decision_map.get("stock_availability", {}).get("outcome")
        if outcome == "out_of_stock":
            _require(
                errors,
                _contains(text, "out of stock"),
                "Stock draft must say the item is out of stock",
            )
            _require(
                errors,
                _contains(
                    text, "no confirmed restock", "no confirmed restock date", "no confirmed eta"
                ),
                "Stock draft must say there is no confirmed restock date",
            )
        _require(
            errors,
            _cited(inline_ids, inventory_id),
            "Live stock claim must cite the inventory record",
        )

    if "return_eligibility" in intents:
        outcome = decision_map.get("return_eligibility", {}).get("outcome")
        if outcome == "eligible":
            _require(
                errors,
                _contains(text, "30-day", "30 day"),
                "Return draft must state the 30-day window",
            )
            _require(
                errors,
                _contains(text, "delivered yesterday", "delivery was yesterday"),
                "Return draft must state that delivery was yesterday",
            )
            _require(
                errors,
                _contains(text, "delivery date"),
                "Return draft must say the window starts from delivery",
            )
        elif outcome == "UNDEFINED":
            _require(
                errors,
                _contains(text, "review", "confirm", "unable to determine"),
                "Undefined return eligibility must be presented as unresolved",
            )
            for phrase in ("yes, you can", "eligible for a return", "return is approved"):
                if phrase in lower:
                    errors.append(
                        f"Undefined return eligibility cannot be presented as approved: {phrase!r}"
                    )
        _require(errors, "KB-RET-01" in inline_ids, "Return policy claim must cite KB-RET-01")
        _require(errors, _cited(inline_ids, order_id), "Delivery fact must cite the scoped order")

    if intents & {"partial_refund", "coupon_proration"}:
        calculation = calculations[0] if calculations else {}
        output = calculation.get("output_cents")
        _require(errors, output == 8000, "Deterministic partial-refund output must be 8000 cents")
        _require(errors, "SGD 80.00" in text, "Draft must copy the SGD 80.00 refund exactly")
        _require(errors, "SGD 20.00" in text, "Draft must state the SGD 20.00 coupon allocation")
        _require(errors, "SGD 8.00" in text, "Draft must state the SGD 8.00 shipping charge")
        _require(
            errors,
            _contains(text, "not refunded"),
            "Draft must say partial-return shipping is not refunded",
        )
        _require(errors, "KB-REF-01" in inline_ids, "Refund policy must cite KB-REF-01")
        _require(errors, _cited(inline_ids, order_id), "Order amounts must cite the scoped order")
        _require(errors, "CALC-L4" in inline_ids, "Exact refund must cite CALC-L4")

    if "defect_return" in intents:
        _require(
            errors,
            _contains(text, "verified") and "order" in lower and "photo" in lower,
            "L5 must acknowledge that the order and photos were verified",
        )
        _require(errors, _cited(inline_ids, order_id), "Verified order fact must cite the order")
        _require(
            errors,
            bool(attachment_ids & inline_ids),
            "Verified photo claim must cite a verified attachment",
        )
        _require(
            errors, _contains(text, "out of stock"), "L5 must state the immediate stock constraint"
        )
        _require(errors, _cited(inline_ids, inventory_id), "L5 stock claim must cite inventory")
        _require(errors, "refund" in lower, "L5 must offer a refund path")
        _require(
            errors,
            "comparable" in lower and _contains(text, "in-stock", "in stock"),
            "L5 must offer a comparable confirmed in-stock alternative",
        )
        _require(
            errors,
            "exact" in lower and "refund" in lower and "breakdown" in lower,
            "L5 must defer the exact refund breakdown",
        )
        _require(
            errors,
            _cited(inline_ids, ledger_id) and "KB-PTS-01" in inline_ids,
            "Unresolved points treatment must cite the ledger and KB-PTS-01",
        )
        _require(
            errors,
            "compensation" in lower and "review" in lower,
            "L5 must describe compensation as under review",
        )
        _require(
            errors,
            _cited(inline_ids, history_id) and "KB-GDW-01" in inline_ids,
            "Compensation review must cite history and goodwill policy",
        )
        _require(
            errors,
            "prefer" in lower or "preference" in lower or "choose" in lower,
            "L5 must ask for the customer's remedy preference",
        )
        _require(
            errors,
            "return" in lower and "review" in lower,
            "Undefined return precedence must remain under review",
        )
        if decision_map.get("D4_refund_composition", {}).get("outcome") == "UNDEFINED":
            if re.search(r"(?:SGD|S\$|\$)\s*\d", text, re.IGNORECASE):
                errors.append(
                    "L5 must not invent a refund or compensation amount while D4 is undefined"
                )
        unsafe = (
            "can proceed with the return",
            "return is approved",
            "approved your return",
            "we have processed",
            "we've processed",
            "refund has been issued",
            "replacement has been sent",
            "compensation coupon has been granted",
        )
        for phrase in unsafe:
            if phrase in lower:
                errors.append(f"Unapproved or unexecuted action language is forbidden: {phrase!r}")
        for phrase in (
            "company a",
            "marketplace seller",
            "policy precedence",
            "seller policy",
            "funding allocation",
        ):
            if phrase in lower:
                errors.append(f"Customer draft exposes internal-only detail: {phrase!r}")

    expected_intents = intents
    covered = set(draft.get("answered_intents", [])) | set(draft.get("unanswered_intents", []))
    missing_intents = sorted(expected_intents - covered)
    if missing_intents:
        errors.append(f"Draft omitted classified intents: {missing_intents}")

    passed = not errors
    return {
        "passed": passed,
        "errors": errors,
        "repair_count": repair_count,
        "checks": {
            "available_source_count": len(valid_sources),
            "inline_citation_count": len(inline_ids),
            "citation_integrity": not (
                unknown_inline or unknown_metadata or missing_inline or undocumented_inline
            ),
            "authority_consistent": not any("Unapproved" in error for error in errors),
            "deterministic_values_consistent": not any(
                "exact" in error.casefold() or "8000" in error for error in errors
            ),
        },
        "send_allowed": passed and not authority.get("requires_human", True),
    }
