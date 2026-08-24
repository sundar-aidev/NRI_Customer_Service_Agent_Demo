from __future__ import annotations

import copy
from typing import Any

from pipeline.schemas import INTENTS


RESPONSES = {
    "warranty": {
        "text": "Small kitchen appliances have a 24-month warranty from delivery for defects arising during normal use. Damage caused by misuse is not covered. [KB-WAR-01]",
        "sources": ["KB-WAR-01"],
        "intents": ["warranty_terms"],
    },
    "stock": {
        "text": "The Aeromix 500 blender is out of stock across all checked locations, and there is no confirmed restock date. [SKU-AER500]",
        "sources": ["SKU-AER500"],
        "intents": ["stock_availability"],
    },
    "return": {
        "text": "Yes. Your order was delivered yesterday [ORD-10023998], so it is within the 30-day return window, which starts from the delivery date. [KB-RET-01]",
        "sources": ["ORD-10023998", "KB-RET-01"],
        "intents": ["return_eligibility"],
    },
    "partial": {
        "text": "Your refund for the SGD 100.00 earbuds is SGD 80.00: the allocated coupon is SGD 20.00. Because this is a partial return, the SGD 8.00 shipping charge is not refunded. [ORD-10024090] [KB-REF-01] [CALC-L4]",
        "sources": ["ORD-10024090", "KB-REF-01", "CALC-L4"],
        "intents": ["partial_refund", "coupon_proration"],
    },
    "damage": {
        "text": (
            "I'm sorry the product arrived damaged. We have verified your order and the attached photos. "
            "[ORD-10024120] [ATT-24120-FRONT] [ATT-24120-SIDE]\n\n"
            "Your return request is under final review. [KB-RET-01]\n\n"
            "The same product is out of stock, so an immediate replacement is not available. "
            "[SKU-AER500] [KB-STK-01] You can choose a refund or a comparable, confirmed in-stock item.\n\n"
            "Because the purchase used a coupon and loyalty points, the exact refund breakdown will be "
            "confirmed during review before anything is processed. "
            "[ORD-10024120] [PTS-LEDGER-C8891] [KB-REF-01] [KB-PTS-01]\n\n"
            "Your compensation request is also under review. [HIST-C8891] [KB-GDW-01] "
            "Please tell us whether you prefer a refund or a comparable in-stock alternative."
        ),
        "sources": [
            "ORD-10024120",
            "ATT-24120-FRONT",
            "ATT-24120-SIDE",
            "KB-RET-01",
            "SKU-AER500",
            "KB-STK-01",
            "PTS-LEDGER-C8891",
            "KB-REF-01",
            "KB-PTS-01",
            "HIST-C8891",
            "KB-GDW-01",
        ],
        "intents": [
            "defect_return",
            "remedy_ownership",
            "replacement",
            "refund_composition",
            "goodwill_compensation",
        ],
    },
}


class StubProvider:
    metadata = {"provider": "test_stub", "model": "deterministic", "auth": "none"}

    def __init__(self, *, bad_generation: bool = False) -> None:
        self.bad_generation = bad_generation
        self.calls: list[str] = []

    def generate_json(self, purpose: str, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(purpose)
        if purpose == "classification":
            return {
                "primary_intent": "warranty_terms",
                "secondary_intents": [],
                "confidence": 0.98,
                "requirements": ["K"],
                "entities": {
                    "customer_id": "",
                    "order_id": "",
                    "product_names": [],
                    "item_names": [],
                },
                "knowledge_families": ["defects_warranties"],
                "lookup_needs": [],
                "decision_needs": ["warranty_terms"],
                "autonomy_candidate": "auto_draft_internal",
                "risk_flags": [],
                "missing_information": [],
            }
        if self.bad_generation:
            response = {
                "text": "We approved everything and issued SGD 99.99. [MADE-UP]",
                "sources": ["MADE-UP"],
                "intents": list(INTENTS),
            }
        elif "What's the warranty on small kitchen appliances" in prompt:
            response = RESPONSES["warranty"]
        elif "Is the Aeromix 500 blender back in stock?" in prompt:
            response = RESPONSES["stock"]
        elif "Can I still return this? It arrived yesterday." in prompt:
            response = RESPONSES["return"]
        elif "I'm returning the SGD 100 wireless earbuds" in prompt:
            response = RESPONSES["partial"]
        else:
            response = RESPONSES["damage"]
        return {
            "text": response["text"],
            "citations": [
                {"source_id": source_id, "claim": f"Grounded claim from {source_id}"}
                for source_id in response["sources"]
            ],
            "answered_intents": response["intents"],
            "unanswered_intents": [],
        }


def cloned_store(store: dict[str, dict]) -> dict[str, dict]:
    return copy.deepcopy(store)
