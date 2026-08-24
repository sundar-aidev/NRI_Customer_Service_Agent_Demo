"""Load runtime-safe eval inputs independently from evaluator-only gold."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_CASES_PATH = ROOT / "evals" / "runtime_cases.json"

FORBIDDEN_RUNTIME_KEYS = {
    "gold",
    "knowledge_ids",
    "record_ids",
    "resolvable_lookups",
    "expected_intents",
    "expected_requirements",
    "expected_knowledge_ids",
    "expected_record_ids",
    "expected_decisions",
    "required_answer_facts",
}


def _load(path: Path) -> list[dict[str, Any]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ValueError(f"{path.name} must contain an array of objects")
    return value


def load_runtime_cases(path: Path = RUNTIME_CASES_PATH) -> list[dict[str, Any]]:
    cases = _load(path)
    seen: set[str] = set()
    for case in cases:
        case_id = case.get("id")
        if not isinstance(case_id, str) or not case_id:
            raise ValueError("every runtime case requires a non-empty id")
        if case_id in seen:
            raise ValueError(f"duplicate runtime case id: {case_id}")
        seen.add(case_id)
        leaked = sorted(FORBIDDEN_RUNTIME_KEYS & set(case))
        if leaked:
            raise ValueError(f"runtime case {case_id} leaks evaluator fields: {leaked}")
        if not isinstance(case.get("query"), str) or not case["query"].strip():
            raise ValueError(f"runtime case {case_id} requires a query")
    return cases


def runtime_case_map() -> dict[str, dict[str, Any]]:
    return {case["id"]: case for case in load_runtime_cases()}
