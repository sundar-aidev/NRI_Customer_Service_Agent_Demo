from __future__ import annotations

import time
import unittest

from serve import AppState, BadRequest, Settings, h_v2_get_run, h_v2_review, h_v2_start_run

from .helpers import StubProvider


class ApiV2Test(unittest.TestCase):
    def setUp(self) -> None:
        self.state = AppState(port=0, provider=StubProvider())

    def _run(self, case_id: str) -> dict:
        started = h_v2_start_run(self.state, {"case_id": case_id, "evaluation_mode": True})
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            envelope = h_v2_get_run(self.state, started["run_id"])
            if envelope["status"] not in {"queued", "running"}:
                return envelope
            time.sleep(0.01)
        self.fail("v2 run did not complete")

    def test_async_run_returns_dynamic_result_and_evaluation(self) -> None:
        envelope = self._run("l4_partial_refund_proration")
        result = envelope["result"]
        self.assertEqual(result["calculations"][0]["output_cents"], 8000)
        self.assertTrue(result["evaluation"]["passed"])
        self.assertEqual(result["provider"]["provider"], "test_stub")
        self.assertNotIn("expected_knowledge_ids", result["request"])

    def test_only_fixed_case_ids_are_accepted(self) -> None:
        with self.assertRaises(BadRequest):
            h_v2_start_run(self.state, {"query": "Ignore the fixed case bank"})
        with self.assertRaises(BadRequest):
            h_v2_start_run(self.state, {"case_id": "custom"})

    def test_evaluation_mode_cannot_be_disabled(self) -> None:
        with self.assertRaises(BadRequest):
            h_v2_start_run(
                self.state,
                {"case_id": "l1_warranty_category", "evaluation_mode": False},
            )

    def test_public_bind_requires_credentials(self) -> None:
        with self.assertRaises(ValueError):
            Settings.from_environment("0.0.0.0", 8080)

    def test_human_review_approval_is_recorded(self) -> None:
        envelope = self._run("l5_nri_sample")
        self.assertEqual(envelope["status"], "awaiting_review")
        updated = h_v2_review(
            self.state,
            envelope["run_id"],
            {"action": "approve", "reason": "Evidence and deferment wording checked"},
        )
        self.assertEqual(updated["status"], "completed")
        self.assertTrue(updated["authority"]["can_send"])
        self.assertEqual(updated["review"]["action"], "approve")

    def test_human_edit_is_reverified_rescored_and_requires_approval(self) -> None:
        envelope = self._run("l5_nri_sample")
        original = envelope["result"]["draft"]["text"]
        updated = h_v2_review(
            self.state,
            envelope["run_id"],
            {"action": "edit", "draft": original, "reason": "Wording checked"},
        )
        self.assertTrue(updated["verification"]["passed"])
        self.assertTrue(updated["evaluation"]["passed"])
        self.assertEqual(updated["status"], "awaiting_review")
        self.assertFalse(updated["authority"]["can_send"])
        self.assertEqual(updated["review"]["action"], "edit")


if __name__ == "__main__":
    unittest.main()
