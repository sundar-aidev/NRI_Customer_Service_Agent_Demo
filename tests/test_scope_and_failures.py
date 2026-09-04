from __future__ import annotations

import copy
import time
import unittest
from dataclasses import replace
from typing import Any

from knowledge.retriever import load_all
from pipeline.fixtures import load_runtime_cases
from pipeline.model_provider import ModelProviderError
from pipeline.orchestrator import (
    CLASSIFIER_RETRY_BACKOFF_SECONDS,
    PipelineFailure,
    PipelineRunner,
)
from pipeline.verifier import verify_draft
from records.resolver import load_store

from .helpers import StubProvider


class FailingProvider(StubProvider):
    """Fails every classification call; other purposes behave normally."""

    def __init__(self, error: Exception) -> None:
        super().__init__()
        self.error = error

    def generate_json(self, purpose: str, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        if purpose == "classification":
            raise self.error
        return super().generate_json(purpose, prompt, schema)


class FlakyProvider(StubProvider):
    """Fails only the first classification call, as a transient provider would."""

    def __init__(self, error: Exception) -> None:
        super().__init__()
        self.error = error
        self.classification_calls = 0

    def generate_json(self, purpose: str, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        if purpose == "classification":
            self.classification_calls += 1
            if self.classification_calls == 1:
                raise self.error
        return super().generate_json(purpose, prompt, schema)


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


class ClassificationFailureTest(unittest.TestCase):
    """A failed classification must stay diagnosable in the trace and the message."""

    def setUp(self) -> None:
        self.cases = load_runtime_cases()
        self.docs = load_all()
        self.store = load_store()

    def _run(self, provider: object) -> tuple[PipelineFailure, list[dict]]:
        events: list[dict] = []
        runner = PipelineRunner(provider, self.docs, self.store)
        with self.assertRaises(PipelineFailure) as caught:
            runner.run(copy.deepcopy(self.cases[4]), on_event=events.append)
        return caught.exception, events

    def test_failure_message_carries_the_provider_reason(self) -> None:
        exc, _ = self._run(FailingProvider(ModelProviderError("Codex request timed out after 180s")))
        self.assertIn("classification failed after one retry", str(exc))
        self.assertIn("Codex request timed out after 180s", str(exc))

    def test_trace_records_the_failing_stage(self) -> None:
        _, events = self._run(FailingProvider(ModelProviderError("provider unavailable")))
        failed = [event for event in events if event["status"] == "failed"]
        self.assertEqual([event["stage"] for event in failed], ["classification"])
        self.assertEqual(failed[0]["artifact"]["attempt_count"], 2)
        self.assertEqual(len(failed[0]["artifact"]["attempt_errors"]), 2)
        # The stages that did finish stay in the trace for the UI to render.
        self.assertIn("intake", [event["stage"] for event in events if event["status"] == "completed"])

    def test_a_transient_first_attempt_still_succeeds(self) -> None:
        provider = FlakyProvider(ModelProviderError("429 rate limited"))
        result = PipelineRunner(provider, self.docs, self.store).run(copy.deepcopy(self.cases[4]))
        self.assertEqual(provider.classification_calls, 2)
        classification = [
            event
            for event in result["trace"]
            if event["stage"] == "classification" and event["status"] == "completed"
        ]
        self.assertEqual(classification[0]["artifact"]["attempt_count"], 2)

    def test_retry_backs_off_before_the_second_attempt(self) -> None:
        provider = FailingProvider(ModelProviderError("boom"))
        started = time.perf_counter()
        with self.assertRaises(PipelineFailure):
            PipelineRunner(provider, self.docs, self.store).run(copy.deepcopy(self.cases[4]))
        self.assertGreaterEqual(time.perf_counter() - started, CLASSIFIER_RETRY_BACKOFF_SECONDS)


class StageFailureTraceTest(unittest.TestCase):
    """Any stage that dies must close the trace on itself, not vanish."""

    def setUp(self) -> None:
        self.cases = load_runtime_cases()
        self.docs = load_all()
        self.store = load_store()

    def test_generation_timeout_marks_the_generation_stage(self) -> None:
        class GenerationTimeout(StubProvider):
            def generate_json(
                self, purpose: str, prompt: str, schema: dict[str, Any]
            ) -> dict[str, Any]:
                if purpose == "response_generation":
                    raise ModelProviderError("Codex response_generation request timed out after 180s")
                return super().generate_json(purpose, prompt, schema)

        events: list[dict] = []
        runner = PipelineRunner(GenerationTimeout(), self.docs, self.store)
        with self.assertRaises(ModelProviderError):
            runner.run(copy.deepcopy(self.cases[0]), on_event=events.append)
        self.assertEqual(events[-1]["stage"], "generation")
        self.assertEqual(events[-1]["status"], "failed")
        self.assertIn("timed out after 180s", events[-1]["summary"])

    def test_classification_failure_is_not_reported_twice(self) -> None:
        events: list[dict] = []
        runner = PipelineRunner(FailingProvider(ModelProviderError("down")), self.docs, self.store)
        with self.assertRaises(PipelineFailure):
            runner.run(copy.deepcopy(self.cases[0]), on_event=events.append)
        failed = [event for event in events if event["status"] == "failed"]
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0]["stage"], "classification")
