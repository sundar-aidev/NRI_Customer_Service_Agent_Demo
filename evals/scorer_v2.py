"""Evaluator-only scoring. Runtime modules must never import this file."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

STOP = {"a", "an", "and", "are", "be", "for", "is", "of", "the", "to", "was"}
GOLD_LABELS_PATH = Path(__file__).resolve().with_name("gold_labels.json")


def _load_gold_labels(path: Path = GOLD_LABELS_PATH) -> dict[str, dict[str, Any]]:
    """Evaluator-owned loader; runtime pipeline modules have no gold path."""
    labels = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(labels, list) or not all(isinstance(item, dict) for item in labels):
        raise ValueError("gold_labels.json must contain an array of objects")
    out: dict[str, dict[str, Any]] = {}
    for label in labels:
        case_id = label.get("id")
        if not isinstance(case_id, str) or not case_id:
            raise ValueError("every gold label requires a non-empty id")
        if case_id in out:
            raise ValueError(f"duplicate gold label id: {case_id}")
        out[case_id] = label
    return out


def _fact_present(text: str, fact: str) -> bool:
    normalized_text = text.casefold().replace("‑", "-").replace("–", "-")
    normalized_fact = fact.casefold().replace("‑", "-").replace("–", "-")
    if normalized_fact in normalized_text:
        return True
    fact_tokens = [
        token for token in re.findall(r"[a-z0-9]+", normalized_fact) if token not in STOP
    ]
    text_tokens = set(re.findall(r"[a-z0-9]+", normalized_text))
    return bool(fact_tokens) and all(token in text_tokens for token in fact_tokens)


def _result(name: str, passed: bool, details: dict[str, Any]) -> dict[str, Any]:
    return {"stage": name, "status": "pass" if passed else "fail", "passed": passed, **details}


class Evaluator:
    def __init__(self) -> None:
        self._gold = _load_gold_labels()

    def score(self, case_id: str, runtime_result: dict[str, Any]) -> dict[str, Any]:
        gold = self._gold[case_id]
        classification = runtime_result["classification"]
        actual_intents = {
            classification["primary_intent"],
            *classification.get("secondary_intents", []),
        }
        expected_intents = set(gold["expected_intents"])
        actual_requirements = set(classification.get("requirements", []))
        expected_requirements = set(gold["expected_requirements"])
        e1_pass = (
            actual_intents == expected_intents and actual_requirements == expected_requirements
        )
        e1 = _result(
            "Classification",
            e1_pass,
            {
                "intent_match": actual_intents == expected_intents,
                "requirements_match": actual_requirements == expected_requirements,
                "actual_intents": sorted(actual_intents),
                "actual_requirements": [
                    item for item in ("K", "T", "C", "D") if item in actual_requirements
                ],
            },
        )

        evidence = runtime_result["evidence"]
        actual_k = {item["source_id"] for item in evidence.get("knowledge", [])}
        actual_t = {item["source_id"] for item in evidence.get("transactions", [])}
        expected_k = set(gold["expected_knowledge_ids"])
        expected_t = set(gold["expected_record_ids"])
        context_customer = (
            runtime_result["request"].get("conversation_context", {}).get("customer_id")
        )
        scoped = True
        if context_customer:
            for record in evidence.get("transactions", []):
                scope_customer = record.get("access_scope", {}).get("customer_id")
                if scope_customer and scope_customer != context_customer:
                    scoped = False
        e2_pass = (
            actual_k == expected_k
            and actual_t == expected_t
            and scoped
            and not evidence.get("unresolved")
        )
        e2 = _result(
            "Retrieval",
            e2_pass,
            {
                "knowledge_exact": actual_k == expected_k,
                "transactions_exact": actual_t == expected_t,
                "customer_scope_valid": scoped,
                "actual_knowledge_ids": sorted(actual_k),
                "actual_record_ids": sorted(actual_t),
                "unresolved": evidence.get("unresolved", []),
            },
        )

        decision_map = {
            item["decision_id"]: item["outcome"] for item in runtime_result["decisions"]
        }
        decision_matches = {
            key: decision_map.get(key) == value
            for key, value in gold.get("expected_decisions", {}).items()
        }
        dependency_order_ok = True
        if case_id == "l5_nri_sample":
            actual_order = [
                item["decision_id"]
                for item in runtime_result["decisions"]
                if item["decision_id"].startswith("D")
            ]
            dependency_order_ok = actual_order == [
                "D1_return_eligibility",
                "D2_remedy_ownership",
                "D3_replacement_remedy",
                "D4_refund_composition",
                "D5_goodwill",
            ]
        e3_pass = all(decision_matches.values()) and dependency_order_ok
        e3 = _result(
            "Decisions",
            e3_pass,
            {
                "decision_matches": decision_matches,
                "dependency_order_valid": dependency_order_ok,
                "actual_outcomes": decision_map,
                "calculations": runtime_result.get("calculations", []),
            },
        )

        text = runtime_result.get("draft", {}).get("text", "")
        missing_facts = [
            fact for fact in gold.get("required_answer_facts", []) if not _fact_present(text, fact)
        ]
        verification = runtime_result.get("verification", {})
        e4_pass = bool(verification.get("passed")) and not missing_facts
        e4 = _result(
            "Response grounding",
            e4_pass,
            {
                "verification_passed": bool(verification.get("passed")),
                "missing_required_facts": missing_facts,
                "verification_errors": verification.get("errors", []),
            },
        )

        actual_human = bool(runtime_result.get("authority", {}).get("requires_human"))
        expected_human = bool(gold["requires_human"])
        unsafe_send = actual_human and bool(
            runtime_result.get("verification", {}).get("send_allowed")
        )
        e5_pass = actual_human == expected_human and not unsafe_send
        e5 = _result(
            "Authority and safety",
            e5_pass,
            {
                "human_gate_match": actual_human == expected_human,
                "requires_human": actual_human,
                "unsafe_send": unsafe_send,
            },
        )

        words = len(text.split())
        quality_pass = 8 <= words <= 220 and not text.strip().endswith("Kind regards,")
        e6 = _result(
            "Customer quality",
            quality_pass,
            {
                "reported_separately": True,
                "word_count": words,
                "notes": []
                if quality_pass
                else ["Draft is empty, too long, or uses an unnecessary formal sign-off."],
            },
        )

        stages = {"E1": e1, "E2": e2, "E3": e3, "E4": e4, "E5": e5, "E6": e6}
        return {
            **stages,
            "passed": all(stages[key]["passed"] for key in ("E1", "E2", "E3", "E4", "E5")),
            "critical_groups": ["E1", "E2", "E3", "E4", "E5"],
        }
