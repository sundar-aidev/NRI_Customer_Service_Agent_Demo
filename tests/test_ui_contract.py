from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class UiContractTest(unittest.TestCase):
    def test_eval_ui_has_no_prebaked_response_or_case_evidence(self) -> None:
        template = (ROOT / "page" / "template.html").read_text(encoding="utf-8")
        cases_block = template.split("const cases = [", 1)[1].split("const SNAPSHOT", 1)[0]
        self.assertNotIn("response:", cases_block)
        self.assertNotIn("transaction:", cases_block)
        self.assertNotIn("knowledge:", cases_block)
        self.assertNotIn("expected_knowledge_ids", template)

    def test_eval_ui_uses_query_driven_v2_api(self) -> None:
        template = (ROOT / "page" / "template.html").read_text(encoding="utf-8")
        self.assertIn("/api/v2/runs", template)
        self.assertNotIn('fetch("/api/case"', template)
        self.assertNotIn('fetch("/api/run"', template)

    def test_run_ui_uses_six_persistent_product_phases(self) -> None:
        template = (ROOT / "page" / "template.html").read_text(encoding="utf-8")
        self.assertEqual(template.count('class="run-stage" data-phase='), 6)
        for phase in ("intake", "classify", "retrieve", "decide", "draft", "verify"):
            self.assertIn(f'data-phase="{phase}"', template)
        self.assertIn("const PIPELINE_PHASES = [", template)
        self.assertIn("function runtimeView(caseId)", template)

    def test_live_polling_patches_stable_surfaces(self) -> None:
        template = (ROOT / "page" / "template.html").read_text(encoding="utf-8")
        polling = template.split("async function waitForPipeline", 1)[1].split(
            "async function runCaseById", 1
        )[0]
        self.assertIn("envelopeSignature(envelope)", polling)
        self.assertIn("patchCaseListState(caseId)", polling)
        self.assertIn("patchPipelineContext()", polling)
        self.assertIn("renderContext(null, true)", polling)
        self.assertNotIn("renderCaseList(", polling)
        self.assertNotIn(
            "renderConversation(true)",
            polling.split("while", 1)[1].split("if (envelope.status", 1)[0],
        )

    def test_rerun_preserves_the_last_verified_draft(self) -> None:
        template = (ROOT / "page" / "template.html").read_text(encoding="utf-8")
        runner = template.split("async function runCaseById", 1)[1].split(
            "async function runSelectedCase", 1
        )[0]
        self.assertNotIn("resultMap.delete", runner)
        self.assertIn("isRefreshing: isRunning && Boolean(result && result.draft)", template)
        self.assertIn('responseState = view.isRefreshing ? "refreshing" : "running"', template)
        self.assertIn("workspace.dataset.state = responseState", template)
        self.assertIn("if (resultMap.has(selectedCaseId)) resetRunStageProgress()", template)
        self.assertIn("dismissToast();", template)

    def test_pipeline_context_is_a_fixed_incremental_ledger(self) -> None:
        template = (ROOT / "page" / "template.html").read_text(encoding="utf-8")
        self.assertIn(r"id=\"pipelineLedger\"", template)
        self.assertIn("function patchPipelineContext()", template)
        self.assertIn("selectedPipelinePhase", template)
        self.assertIn("pipelinePhasePinned", template)

    def test_response_review_and_evaluation_have_distinct_surfaces(self) -> None:
        template = (ROOT / "page" / "template.html").read_text(encoding="utf-8")
        conversation = template.split("function renderConversation(showResponse)", 1)[1].split(
            "function renderRunState", 1
        )[0]
        self.assertIn('id=\\"editDraftInline\\"', conversation)
        self.assertNotIn("evalMarkup(result)", conversation)
        self.assertNotIn("decision-banner", conversation)
        self.assertIn('id="reviewBar"', template)
        self.assertIn('id="viewEvaluation"', template)
        self.assertIn('selectedPipelinePhase = "verify"', template)
        self.assertIn("function evaluationDetailMarkup(result)", template)
        for group in ("E1", "E2", "E3", "E4", "E5", "E6"):
            self.assertIn(f'"{group}"', template)

    def test_completed_runtime_auto_selects_verify(self) -> None:
        template = (ROOT / "page" / "template.html").read_text(encoding="utf-8")
        runtime = template.split("function runtimeView(caseId)", 1)[1].split("function setText", 1)[
            0
        ]
        self.assertIn('result ? "complete" : "intake"', runtime)

    def test_tabsets_have_keyboard_roving_focus(self) -> None:
        template = (ROOT / "page" / "template.html").read_text(encoding="utf-8")
        self.assertIn("function bindRovingTabs(container, items, activate)", template)
        for key in ("ArrowRight", "ArrowLeft", "Home", "End"):
            self.assertIn(f'event.key === "{key}"', template)
        self.assertIn(
            'contextContent.setAttribute("aria-labelledby", selectedTab + "Tab")', template
        )
        self.assertIn('dataLayerContent.setAttribute("aria-labelledby"', template)

    def test_file_snapshot_redirects_to_local_live_app(self) -> None:
        template = (ROOT / "page" / "template.html").read_text(encoding="utf-8")
        self.assertIn(
            'openedFromFile ? "http://127.0.0.1:8765/" : window.location.origin + "/"', template
        )
        self.assertIn('openedFromFile ? "Open live app" : "Retry connection"', template)

    def test_hosted_ui_does_not_mutate_knowledge(self) -> None:
        template = (ROOT / "page" / "template.html").read_text(encoding="utf-8")
        self.assertNotIn("/api/knowledge/reset", template)
        self.assertNotIn('method: "PUT"', template)
        self.assertIn("read-only evidence snapshot", template)


if __name__ == "__main__":
    unittest.main()
