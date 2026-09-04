"""Query-to-response orchestration with stage-level, replayable traces."""

from __future__ import annotations

import copy
import hashlib
import json
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from knowledge.retriever import Document

from .classifier import classify
from .decisions import apply_decisions
from .evidence import normalize_evidence
from .generator import generate_draft
from .knowledge_search import search_knowledge
from .model_provider import JsonModelProvider, ModelProviderError
from .retrieval_planner import plan_retrieval
from .verifier import verify_draft


TraceCallback = Callable[[dict[str, Any]], None]

CLASSIFIER_ATTEMPTS = 2
CLASSIFIER_RETRY_BACKOFF_SECONDS = 1.5


class PipelineFailure(RuntimeError):
    """Safe, user-facing pipeline failure."""


def _failure_reason(errors: list[str]) -> str:
    """Build an actionable classification failure message.

    The provider already scrubs credentials from its errors, so the detail is
    safe to surface. Without it the operator only learns that something failed.
    """
    detail = errors[-1].strip() if errors and errors[-1].strip() else "no detail reported"
    retries = max(len(errors) - 1, 0)
    label = "one retry" if retries == 1 else f"{retries} retries"
    return f"classification failed after {label}: {detail}"


def _emit_stage_failure(
    events: list[dict[str, Any]], emit: Callable[..., None], exc: BaseException
) -> None:
    """Close the trace on the stage that was running when the run died.

    Without this the UI sees a run that failed with no stage ever marked, and
    renders it as if the pipeline had never started.
    """
    last = events[-1] if events else None
    if last is not None and last["status"] == "failed":
        return  # the stage already reported its own failure in detail
    stage = last["stage"] if last is not None else "intake"
    emit(stage, "failed", str(exc) or exc.__class__.__name__)


class PipelineRunner:
    def __init__(
        self, provider: JsonModelProvider, docs: dict[str, Document], store: dict[str, dict]
    ) -> None:
        self.provider = provider
        self.docs = copy.deepcopy(docs)
        self.store = copy.deepcopy(store)

    def _source_snapshot(self) -> str:
        payload = {
            "knowledge": {
                source_id: {
                    "version": doc.version,
                    "status": doc.status,
                    "body": doc.body,
                    "params": doc.params,
                }
                for source_id, doc in sorted(self.docs.items())
            },
            "records": self.store,
        }
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[
            :16
        ]
        return f"snapshot_{digest}"

    @staticmethod
    def _validate_request(request: dict[str, Any]) -> dict[str, Any]:
        forbidden = {
            "gold",
            "knowledge_ids",
            "record_ids",
            "expected_intents",
            "expected_requirements",
            "expected_knowledge_ids",
            "expected_record_ids",
            "expected_decisions",
            "required_answer_facts",
            "response",
            "answer",
        }
        leaked = sorted(forbidden & set(request))
        if leaked:
            raise PipelineFailure(f"runtime request contains evaluator-only fields: {leaked}")
        query = request.get("query")
        if not isinstance(query, str) or not query.strip():
            raise PipelineFailure("query is required")
        context = request.get("conversation_context") or {}
        if not isinstance(context, dict):
            raise PipelineFailure("conversation_context must be an object")
        attachments = request.get("attachments") or []
        if not isinstance(attachments, list):
            raise PipelineFailure("attachments must be an array")
        for attachment in attachments:
            if not isinstance(attachment, dict) or attachment.get("certainty") not in {
                "provided",
                "machine_observed",
                "human_verified",
            }:
                raise PipelineFailure("each attachment requires a valid certainty")
        return {
            "case_id": str(request.get("case_id") or request.get("id") or "custom"),
            "query": query.strip(),
            "channel": str(request.get("channel") or "marketplace_chat"),
            "locale": str(request.get("locale") or "en-SG"),
            "conversation_context": copy.deepcopy(context),
            "attachments": copy.deepcopy(attachments),
            "evaluation_mode": bool(request.get("evaluation_mode", False)),
        }

    def run(
        self,
        request: dict[str, Any],
        *,
        run_id: str | None = None,
        trace_id: str | None = None,
        on_event: TraceCallback | None = None,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        safe_request = self._validate_request(request)
        run_id = run_id or f"run_{uuid.uuid4().hex[:12]}"
        trace_id = trace_id or f"trace_{uuid.uuid4().hex[:12]}"
        events: list[dict[str, Any]] = []

        def emit(
            stage: str, status: str, summary: str, artifact: dict[str, Any] | None = None
        ) -> None:
            event = {
                "sequence": len(events) + 1,
                "stage": stage,
                "status": status,
                "summary": summary,
                "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
            }
            if artifact is not None:
                event["artifact"] = copy.deepcopy(artifact)
            events.append(event)
            if on_event:
                on_event(copy.deepcopy(event))

        try:
            return self._run_stages(safe_request, run_id, trace_id, started, events, emit)
        except Exception as exc:
            # Any stage can die on a provider timeout or outage. Close the trace
            # on the stage that was running so the failure stays locatable.
            _emit_stage_failure(events, emit, exc)
            raise

    def _run_stages(
        self,
        safe_request: dict[str, Any],
        run_id: str,
        trace_id: str,
        started: float,
        events: list[dict[str, Any]],
        emit: Callable[..., None],
    ) -> dict[str, Any]:
        emit(
            "intake",
            "completed",
            "Validated query, authorized context, and attachment certainty",
            {
                "query_hash": hashlib.sha256(safe_request["query"].encode("utf-8")).hexdigest()[
                    :16
                ],
                "authorized_context_ids": {
                    key: safe_request["conversation_context"].get(key)
                    for key in ("customer_id", "active_order_id")
                    if safe_request["conversation_context"].get(key)
                },
                "attachment_count": len(safe_request["attachments"]),
            },
        )

        emit("classification", "running", "Model is decomposing the customer request")
        classification = None
        classifier_errors: list[str] = []
        for attempt in range(CLASSIFIER_ATTEMPTS):
            try:
                classification = classify(safe_request, self.provider)
                break
            except (ModelProviderError, ValueError) as exc:
                classifier_errors.append(str(exc))
                if attempt == CLASSIFIER_ATTEMPTS - 1:
                    reason = _failure_reason(classifier_errors)
                    # Record where the run died so the trace stays readable
                    # instead of collapsing back to an untouched pipeline.
                    emit(
                        "classification",
                        "failed",
                        reason,
                        {
                            "attempt_count": len(classifier_errors),
                            "attempt_errors": list(classifier_errors),
                        },
                    )
                    raise PipelineFailure(reason) from exc
                # A retry that fires instantly re-hits the same transient
                # provider condition (rate limit, timeout, cold start).
                time.sleep(CLASSIFIER_RETRY_BACKOFF_SECONDS)
        assert classification is not None
        emit(
            "classification",
            "completed",
            (
                f"Classified {1 + len(classification['secondary_intents'])} intent(s) requiring "
                f"{' + '.join(classification['requirements']) or 'no external capability'}"
            ),
            {
                "primary_intent": classification["primary_intent"],
                "secondary_intents": classification["secondary_intents"],
                "requirements": classification["requirements"],
                "confidence": classification["confidence"],
                "normalization_changes": classification.get("normalization_changes", {}),
                "attempt_count": len(classifier_errors) + 1,
            },
        )

        emit("retrieval_planning", "running", "Converting intent needs into typed K and T requests")
        retrieval_plan = plan_retrieval(classification, safe_request)
        emit(
            "retrieval_planning",
            "completed",
            (
                f"Planned {len(retrieval_plan['knowledge_requests'])} knowledge search(es) and "
                f"{len(retrieval_plan['transaction_requests'])} scoped tool call(s)"
            ),
            retrieval_plan,
        )

        emit(
            "knowledge_retrieval",
            "running",
            "Ranking governed documents from query and policy family",
        )
        emit(
            "transaction_retrieval",
            "running",
            "Executing allow-listed, customer-scoped record lookups",
        )
        with ThreadPoolExecutor(max_workers=2, thread_name_prefix="nri-retrieval") as pool:
            knowledge_future = pool.submit(search_knowledge, retrieval_plan, self.docs)
            transaction_future = pool.submit(execute_transaction_plan, retrieval_plan, self.store)
            knowledge_result = knowledge_future.result()
            transaction_result = transaction_future.result()
        emit(
            "knowledge_retrieval",
            "completed",
            (f"Selected {len(knowledge_result['selected'])} governed source(s)"),
            {
                "selected_ids": [item["source_id"] for item in knowledge_result["selected"]],
                "queries": knowledge_result["queries"],
                "unresolved": knowledge_result["unresolved"],
            },
        )
        emit(
            "transaction_retrieval",
            "completed",
            (f"Selected {len(transaction_result['selected'])} scoped record(s)"),
            {
                "selected_ids": [item["source_id"] for item in transaction_result["selected"]],
                "calls": transaction_result["calls"],
                "unresolved": transaction_result["unresolved"],
            },
        )

        emit(
            "evidence_normalization",
            "running",
            "Freezing selected passages, fields, gaps, and conflicts",
        )
        evidence = normalize_evidence(safe_request, knowledge_result, transaction_result)
        emit(
            "evidence_normalization",
            "completed",
            f"Frozen evidence snapshot {evidence['snapshot_hash']}",
            {
                "snapshot_hash": evidence["snapshot_hash"],
                "policy_gap_count": len(evidence["policy_gaps"]),
                "conflict_count": len(evidence["conflicts"]),
                "unresolved_count": len(evidence["unresolved"]),
            },
        )

        emit(
            "decisioning",
            "running",
            "Applying deterministic rules, calculations, and dependency gates",
        )
        decision_result = apply_decisions(safe_request, classification, evidence)
        decisions = decision_result["decisions"]
        calculations = decision_result["calculations"]
        authority = decision_result["authority"]
        emit(
            "decisioning",
            "completed",
            (f"Produced {len(decisions)} decision(s) and {len(calculations)} exact calculation(s)"),
            {"decisions": decisions, "calculations": calculations, "authority": authority},
        )

        emit("generation", "running", "Generating a customer-safe response from frozen evidence")
        draft = generate_draft(
            safe_request,
            classification,
            evidence,
            decisions,
            calculations,
            authority,
            self.provider,
        )
        emit(
            "generation",
            "completed",
            f"Generated {len(draft['citations'])} cited source reference(s)",
            {
                "citation_ids": [item["source_id"] for item in draft["citations"]],
                "answered_intents": draft["answered_intents"],
                "unanswered_intents": draft["unanswered_intents"],
            },
        )

        emit(
            "verification",
            "running",
            "Checking citations, exact values, safety, and decision authority",
        )
        verification = verify_draft(
            safe_request,
            classification,
            evidence,
            decisions,
            calculations,
            authority,
            draft,
            0,
        )
        if not verification["passed"]:
            emit(
                "verification",
                "repairing",
                "First verification failed; requesting one constrained repair",
                {
                    "errors": verification["errors"],
                },
            )
            try:
                draft = generate_draft(
                    safe_request,
                    classification,
                    evidence,
                    decisions,
                    calculations,
                    authority,
                    self.provider,
                    previous=draft,
                    verification_errors=verification["errors"],
                )
                verification = verify_draft(
                    safe_request,
                    classification,
                    evidence,
                    decisions,
                    calculations,
                    authority,
                    draft,
                    1,
                )
            except (ModelProviderError, ValueError) as exc:
                verification = {
                    **verification,
                    "passed": False,
                    "repair_count": 1,
                    "errors": [*verification["errors"], f"Constrained repair failed: {exc}"],
                    "send_allowed": False,
                }
        emit(
            "verification",
            "completed" if verification["passed"] else "blocked",
            (
                "Grounding and safety checks passed"
                if verification["passed"]
                else "Verification remained blocked after the allowed repair"
            ),
            verification,
        )

        if not verification["passed"]:
            authority = {
                **authority,
                "requires_human": True,
                "state": "awaiting_review",
                "can_send": False,
                "reason": authority["reason"] + "; response verification did not pass",
            }
        status = "awaiting_review" if authority["requires_human"] else "completed"
        active_stage = "approval" if authority["requires_human"] else "complete"
        emit(
            active_stage,
            "awaiting_review" if authority["requires_human"] else "completed",
            (authority["reason"]),
            authority,
        )

        return {
            "run_id": run_id,
            "trace_id": trace_id,
            "status": status,
            "active_stage": active_stage,
            "source_snapshot": self._source_snapshot(),
            "request": safe_request,
            "provider": self.provider.metadata,
            "prompt_versions": {
                "classifier": "classifier_v1",
                "response": "response_v1",
                "repair": "repair_v1",
            },
            "classification": classification,
            "retrieval_plan": retrieval_plan,
            "evidence": evidence,
            "decisions": decisions,
            "calculations": calculations,
            "draft": draft,
            "verification": verification,
            "authority": authority,
            "trace": events,
            "review": {
                "state": "awaiting_review" if authority["requires_human"] else "not_required",
                "original_draft": draft["text"],
                "edited_draft": None,
                "action": None,
                "reason": None,
            },
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
        }


# Local import kept below the class so the two retrieval paths remain visually
# distinct and easy to audit.
from .transaction_tools import execute_transaction_plan  # noqa: E402
