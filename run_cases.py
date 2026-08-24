"""Run the query-driven pipeline using the local ChatGPT-authenticated Codex client.

Examples:
    python3 -B run_cases.py --case l3_return_eligible_join
    python3 -B run_cases.py --all --parallel 2
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from evals.scorer_v2 import Evaluator
from knowledge.retriever import load_all
from pipeline.fixtures import load_runtime_cases
from pipeline.model_provider import CodexOAuthProvider
from pipeline.orchestrator import PipelineRunner
from records.resolver import load_store


def _summary(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "case_id": result["request"]["case_id"],
        "status": result["status"],
        "provider": result["provider"],
        "intents": [
            result["classification"]["primary_intent"],
            *result["classification"]["secondary_intents"],
        ],
        "requirements": result["classification"]["requirements"],
        "knowledge_ids": [item["source_id"] for item in result["evidence"]["knowledge"]],
        "record_ids": [item["source_id"] for item in result["evidence"]["transactions"]],
        "decisions": {item["decision_id"]: item["outcome"] for item in result["decisions"]},
        "verification": result["verification"],
        "evaluation_passed": result.get("evaluation", {}).get("passed"),
        "draft": result["draft"]["text"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the NRI query-to-response pipeline")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--case", help="Runtime case id")
    target.add_argument("--all", action="store_true", help="Run all five cases")
    parser.add_argument("--parallel", type=int, choices=(1, 2), default=1)
    args = parser.parse_args(argv)

    cases = load_runtime_cases()
    if args.case:
        cases = [case for case in cases if case["id"] == args.case]
        if not cases:
            parser.error(f"unknown case id: {args.case}")

    docs = load_all()
    store = load_store()
    provider = CodexOAuthProvider()
    evaluator = Evaluator()

    def execute(case: dict[str, Any]) -> dict[str, Any]:
        print(f"[{case['id']}] running", file=sys.stderr, flush=True)
        result = PipelineRunner(provider, docs, store).run(case)
        result["evaluation"] = evaluator.score(case["id"], result)
        print(
            f"[{case['id']}] {'pass' if result['evaluation']['passed'] else 'finding'} "
            f"({result['verification']['repair_count']} repair)",
            file=sys.stderr,
            flush=True,
        )
        return result

    results: list[dict[str, Any]] = []
    if args.parallel == 1 or len(cases) == 1:
        results = [execute(case) for case in cases]
    else:
        with ThreadPoolExecutor(max_workers=args.parallel, thread_name_prefix="nri-live") as pool:
            futures = {pool.submit(execute, case): case["id"] for case in cases}
            for future in as_completed(futures):
                results.append(future.result())
        order = {case["id"]: index for index, case in enumerate(cases)}
        results.sort(key=lambda result: order[result["request"]["case_id"]])

    print(json.dumps([_summary(result) for result in results], indent=2, ensure_ascii=False))
    return 0 if all(result["evaluation"]["passed"] for result in results) else 1


if __name__ == "__main__":
    sys.exit(main())
