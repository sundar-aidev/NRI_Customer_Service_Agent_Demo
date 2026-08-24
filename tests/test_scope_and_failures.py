from __future__ import annotations

import copy
import unittest
from dataclasses import replace

from knowledge.retriever import load_all
from pipeline.fixtures import load_runtime_cases
from pipeline.orchestrator import PipelineRunner
from pipeline.verifier import verify_draft
from records.resolver import load_store

from .helpers import StubProvider


class ScopeAndFailureTest(unittest.TestCase):
    def setUp(self) -> None:
        self.cases = load_runtime_cases()
        self.docs = load_all()
        self.store = load_store()

    def test_wrong_customer_never_returns_order(self) -> None:
        case = copy.deepcopy(self.cases[2])
        case["conversation_context"]["customer_id"] = "C8891"
        result = PipelineRunner(StubProvider(), self.docs, self.store).run(case)
        self.assertEqual(result["evidence"]["transactions"], [])
        self.assertTrue(
            any("does not belong" in item["reason"] for item in result["evidence"]["unresolved"])
        )
        self.assertTrue(result["authority"]["requires_human"])

    def test_stale_inventory_is_not_used(self) -> None:
        store = copy.deepcopy(self.store)
        store["SKU-AER500"]["freshness"] = "stale"
        result = PipelineRunner(StubProvider(), self.docs, store).run(self.cases[1])
        self.assertEqual(result["evidence"]["transactions"], [])
        self.assertTrue(any("stale" in item["reason"] for item in result["evidence"]["unresolved"]))

    def test_ambiguous_inventory_is_not_guessed(self) -> None:
        store = copy.deepcopy(self.store)
        duplicate = copy.deepcopy(store["SKU-AER500"])
        duplicate["sku"] = "SKU-AER500-B"
        store["SKU-AER500-B"] = duplicate
        result = PipelineRunner(StubProvider(), self.docs, store).run(self.cases[1])
        self.assertEqual(result["evidence"]["transactions"], [])
        self.assertTrue(
            any("ambiguous" in item["reason"] for item in result["evidence"]["unresolved"])
        )

    def test_current_policy_conflict_is_preserved_and_human_owned(self) -> None:
        result = PipelineRunner(StubProvider(), self.docs, self.store).run(self.cases[4])
        self.assertEqual(result["evidence"]["conflicts"][0]["state"], "unresolved")
        self.assertEqual(
            result["evidence"]["conflicts"][0]["sources"],
            ["KB-RET-01", "KB-MKT-01", "KB-PRE-01"],
        )
        self.assertTrue(result["authority"]["requires_human"])

    def test_attachment_filename_alone_is_not_verified_damage(self) -> None:
        case = copy.deepcopy(self.cases[4])
        for attachment in case["attachments"]:
            attachment["certainty"] = "provided"
        result = PipelineRunner(StubProvider(), self.docs, self.store).run(case)
        d1 = next(
            item for item in result["decisions"] if item["decision_id"] == "D1_return_eligibility"
        )
        self.assertEqual(d1["outcome"], "UNDEFINED")
        self.assertIn("verified damage", d1["explanation"].casefold())

    def test_missing_return_window_parameter_never_defaults_to_30(self) -> None:
        docs = dict(self.docs)
        docs["KB-RET-01"] = replace(docs["KB-RET-01"], params={})
        result = PipelineRunner(StubProvider(), docs, self.store).run(self.cases[2])
        decision = next(
            item for item in result["decisions"] if item["decision_id"] == "return_eligibility"
        )
        self.assertEqual(decision["outcome"], "UNDEFINED")
        self.assertTrue(decision["requires_human"])
        self.assertFalse(result["verification"]["passed"])

    def test_missing_refund_parameter_never_guesses_an_amount(self) -> None:
        docs = dict(self.docs)
        docs["KB-REF-01"] = replace(docs["KB-REF-01"], params={})
        result = PipelineRunner(StubProvider(), docs, self.store).run(self.cases[3])
        self.assertEqual(result["decisions"][0]["outcome"], "UNDEFINED")
        self.assertEqual(result["calculations"], [])
        self.assertTrue(result["authority"]["requires_human"])

    def test_missing_goodwill_cap_remains_undefined(self) -> None:
        docs = dict(self.docs)
        docs["KB-GDW-01"] = replace(docs["KB-GDW-01"], params={})
        result = PipelineRunner(StubProvider(), docs, self.store).run(self.cases[4])
        d5 = next(item for item in result["decisions"] if item["decision_id"] == "D5_goodwill")
        self.assertEqual(d5["outcome"], "UNDEFINED")
        self.assertTrue(d5["requires_human"])

    def _reverify(self, result: dict) -> dict:
        return verify_draft(
            result["request"],
            result["classification"],
            result["evidence"],
            result["decisions"],
            result["calculations"],
            result["authority"],
            result["draft"],
            0,
        )

    def test_source_free_live_fact_is_rejected(self) -> None:
        result = PipelineRunner(StubProvider(), self.docs, self.store).run(self.cases[1])
        result["draft"]["text"] = result["draft"]["text"].replace(" [SKU-AER500]", "")
        result["draft"]["citations"] = []
        verification = self._reverify(result)
        self.assertFalse(verification["passed"])
        self.assertTrue(any("inventory record" in error for error in verification["errors"]))

    def test_unknown_citation_is_rejected(self) -> None:
        result = PipelineRunner(StubProvider(), self.docs, self.store).run(self.cases[0])
        result["draft"]["text"] += " [MADE-UP]"
        result["draft"]["citations"].append({"source_id": "MADE-UP", "claim": "Unsupported"})
        verification = self._reverify(result)
        self.assertFalse(verification["passed"])
        self.assertTrue(any("not in frozen evidence" in error for error in verification["errors"]))

    def test_model_cannot_change_deterministic_refund_amount(self) -> None:
        result = PipelineRunner(StubProvider(), self.docs, self.store).run(self.cases[3])
        result["draft"]["text"] = result["draft"]["text"].replace("SGD 80.00", "SGD 81.00")
        verification = self._reverify(result)
        self.assertFalse(verification["passed"])
        self.assertTrue(any("SGD 80.00" in error for error in verification["errors"]))

    def test_unapproved_action_language_is_rejected(self) -> None:
        result = PipelineRunner(StubProvider(), self.docs, self.store).run(self.cases[4])
        result["draft"]["text"] += " Your return is approved."
        verification = self._reverify(result)
        self.assertFalse(verification["passed"])
        self.assertTrue(any("Unapproved" in error for error in verification["errors"]))


if __name__ == "__main__":
    unittest.main()
