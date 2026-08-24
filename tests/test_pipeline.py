from __future__ import annotations

import copy
import unittest
from pathlib import Path

from evals.scorer_v2 import Evaluator
from knowledge.retriever import load_all
from pipeline.fixtures import load_runtime_cases
from pipeline.orchestrator import PipelineFailure, PipelineRunner
from records.resolver import load_store

from .helpers import StubProvider


class PipelineCasesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cases = load_runtime_cases()
        cls.docs = load_all()
        cls.store = load_store()

    def test_all_five_cases_pass_e1_to_e5(self) -> None:
        evaluator = Evaluator()
        for case in self.cases:
            with self.subTest(case=case["id"]):
                provider = StubProvider()
                result = PipelineRunner(provider, self.docs, self.store).run(case)
                result["evaluation"] = evaluator.score(case["id"], result)
                self.assertTrue(result["evaluation"]["passed"], result["evaluation"])
                self.assertEqual(result["provider"]["provider"], "test_stub")
                self.assertEqual(result["request"]["case_id"], case["id"])
                self.assertIn("classification", provider.calls)
                self.assertIn("response_generation", provider.calls)

    def test_runtime_request_rejects_gold_leakage(self) -> None:
        case = copy.deepcopy(self.cases[0])
        case["expected_knowledge_ids"] = ["KB-WAR-01"]
        with self.assertRaises(PipelineFailure):
            PipelineRunner(StubProvider(), self.docs, self.store).run(case)

    def test_runtime_pipeline_has_no_gold_fixture_path(self) -> None:
        pipeline_dir = Path(__file__).resolve().parents[1] / "pipeline"
        runtime_source = "\n".join(
            path.read_text(encoding="utf-8") for path in sorted(pipeline_dir.glob("*.py"))
        )
        self.assertNotIn("gold_labels.json", runtime_source)
        self.assertNotIn("load_gold_labels", runtime_source)

    def test_k_only_case_does_not_access_transactions(self) -> None:
        result = PipelineRunner(StubProvider(), self.docs, self.store).run(self.cases[0])
        self.assertEqual(result["retrieval_plan"]["transaction_requests"], [])
        self.assertEqual(result["evidence"]["transactions"], [])

    def test_t_only_case_does_not_search_knowledge(self) -> None:
        result = PipelineRunner(StubProvider(), self.docs, self.store).run(self.cases[1])
        self.assertEqual(result["retrieval_plan"]["knowledge_requests"], [])
        self.assertEqual(result["evidence"]["knowledge"], [])

    def test_retired_policy_is_excluded(self) -> None:
        result = PipelineRunner(StubProvider(), self.docs, self.store).run(self.cases[2])
        self.assertNotIn(
            "KB-RET-00", {item["source_id"] for item in result["evidence"]["knowledge"]}
        )
        retired = [
            item
            for item in result["evidence"]["excluded_knowledge"]
            if item["source_id"] == "KB-RET-00"
        ]
        self.assertTrue(retired)
        self.assertTrue(all(item["reason"] == "retired" for item in retired))

    def test_l4_calculation_is_exact_integer_cents(self) -> None:
        result = PipelineRunner(StubProvider(), self.docs, self.store).run(self.cases[3])
        calculation = result["calculations"][0]
        self.assertEqual(calculation["output_cents"], 8000)
        self.assertEqual(calculation["inputs"]["allocated_coupon_cents"], 2000)
        self.assertFalse(calculation["inputs"]["shipping_refundable_on_partial"])

    def test_l5_has_ordered_d1_to_d5_and_open_gates(self) -> None:
        result = PipelineRunner(StubProvider(), self.docs, self.store).run(self.cases[4])
        decision_ids = [item["decision_id"] for item in result["decisions"]]
        self.assertEqual(
            decision_ids,
            [
                "D1_return_eligibility",
                "D2_remedy_ownership",
                "D3_replacement_remedy",
                "D4_refund_composition",
                "D5_goodwill",
            ],
        )
        outcomes = {item["decision_id"]: item["outcome"] for item in result["decisions"]}
        self.assertEqual(outcomes["D1_return_eligibility"], "UNDEFINED")
        self.assertEqual(outcomes["D3_replacement_remedy"], "not_feasible")
        self.assertEqual(outcomes["D4_refund_composition"], "UNDEFINED")
        self.assertEqual(result["status"], "awaiting_review")

    def test_second_verification_failure_is_human_gated(self) -> None:
        result = PipelineRunner(StubProvider(bad_generation=True), self.docs, self.store).run(
            self.cases[3]
        )
        self.assertFalse(result["verification"]["passed"])
        self.assertEqual(result["verification"]["repair_count"], 1)
        self.assertEqual(result["status"], "awaiting_review")
        self.assertFalse(result["verification"]["send_allowed"])


if __name__ == "__main__":
    unittest.main()
