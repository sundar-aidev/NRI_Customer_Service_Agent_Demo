"""Governed local knowledge search driven by query and policy family.

This intentionally uses no evaluator labels and accepts no source identifiers.
The small demo corpus is ranked with lexical/concept matching; the contract is
compatible with a future embedding/reranking implementation.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from typing import Any

from knowledge.retriever import Document


TOKEN_RE = re.compile(r"[a-z0-9]+")
STOP = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "the",
    "this",
    "to",
    "when",
    "with",
}

CONCEPTS = {
    "warranty": {"coverage", "covered", "months", "misuse", "category"},
    "return": {"returned", "returns", "eligibility", "window", "delivery"},
    "refund": {"refunded", "composition", "shipping", "coupon", "points"},
    "coupon": {"discount", "apportioned", "allocation", "proration"},
    "points": {"loyalty", "redeemed", "expiry", "expired", "ledger"},
    "seller": {"marketplace", "sale", "responsibility", "fulfilled"},
    "precedence": {"conflict", "undefined", "policy", "seller"},
    "stock": {"inventory", "available", "replacement", "reshipment", "alternative"},
    "goodwill": {"compensation", "coupon", "cap", "approval", "discretionary"},
    "defective": {"defect", "damaged", "return", "sale"},
}


def _tokens(text: str) -> list[str]:
    return [token for token in TOKEN_RE.findall(text.casefold()) if token not in STOP]


def _expanded(text: str) -> Counter[str]:
    base = _tokens(text)
    values = list(base)
    for token in base:
        values.extend(CONCEPTS.get(token, ()))
        for key, synonyms in CONCEPTS.items():
            if token in synonyms:
                values.append(key)
    return Counter(values)


def _best_passage(doc: Document, query_terms: Counter[str]) -> tuple[str, float]:
    passages = [part.strip() for part in re.split(r"\n\s*\n", doc.body) if part.strip()]
    best = ""
    best_score = -1.0
    for passage in passages:
        terms = Counter(_tokens(passage))
        score = sum(min(count, terms.get(term, 0)) for term, count in query_terms.items())
        if score > best_score:
            best, best_score = passage, float(score)
    compact = re.sub(r"\s+", " ", best)
    return compact[:760], best_score


def _score(doc: Document, query: str) -> tuple[float, str]:
    query_terms = _expanded(query)
    title_terms = Counter(_tokens(doc.title))
    body_terms = Counter(_tokens(doc.body))
    title_overlap = sum(min(count, title_terms.get(term, 0)) for term, count in query_terms.items())
    body_overlap = sum(min(count, body_terms.get(term, 0)) for term, count in query_terms.items())
    passage, passage_overlap = _best_passage(doc, query_terms)
    status_bonus = 0.25 if doc.status == "current" else 0.12 if doc.is_gap else -5.0
    score = title_overlap * 3.0 + body_overlap * 0.35 + passage_overlap * 0.8 + status_bonus
    return round(score, 4), passage


def _snapshot_hash(doc: Document) -> str:
    payload = {
        "id": doc.id,
        "version": doc.version,
        "status": doc.status,
        "body": doc.body,
        "params": doc.params,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:16]


def search_knowledge(plan: dict[str, Any], docs: dict[str, Document]) -> dict[str, Any]:
    selected_by_id: dict[str, dict[str, Any]] = {}
    excluded: list[dict[str, Any]] = []
    queries: list[dict[str, Any]] = []

    for request_index, request in enumerate(plan.get("knowledge_requests", []), start=1):
        family = request["family"]
        query = request["query"]
        top_k = max(1, int(request.get("top_k", 1)))
        supports = list(request.get("supports", []))
        candidates: list[tuple[float, str, Document, str]] = []
        for doc in docs.values():
            # Retired documents live under the archive filing axis. Include
            # them only as auditable candidates so a stale lexical hit is
            # visible, while the hard status filter below prevents selection.
            if doc.kind != family and doc.status != "retired":
                continue
            score, passage = _score(doc, query)
            candidates.append((score, doc.id, doc, passage))
        candidates.sort(key=lambda row: (-row[0], row[1]))

        eligible = [row for row in candidates if row[2].status != "retired" and row[0] > 0]
        chosen = eligible[:top_k]
        queries.append(
            {
                "request_index": request_index,
                "family": family,
                "query": query,
                "top_k": top_k,
                "candidate_count": len(candidates),
                "selected_ids": [row[2].id for row in chosen],
                "supports": supports,
            }
        )
        for rank, (score, _doc_id, doc, passage) in enumerate(chosen, start=1):
            existing = selected_by_id.get(doc.id)
            item = {
                "source_id": doc.id,
                "title": doc.title,
                "family": doc.kind,
                "version": doc.version,
                "effective_date": doc.effective_date,
                "status": doc.status,
                "owner": doc.owner,
                "provenance": doc.provenance,
                "provenance_note": doc.provenance_note,
                "matched_passage": passage,
                "body": doc.body,
                "params": dict(doc.params),
                "retrieval_method": "family_filter+lexical_concept_rank",
                "retrieval_score": score,
                "rank": rank,
                "snapshot_hash": _snapshot_hash(doc),
                "supports": supports,
                "selection_state": "selected_gap" if doc.is_gap else "selected",
            }
            if existing is None:
                selected_by_id[doc.id] = item
            else:
                existing["supports"] = list(dict.fromkeys(existing["supports"] + supports))
                if score > existing["retrieval_score"]:
                    existing["retrieval_score"] = score
                    existing["matched_passage"] = passage
                    existing["rank"] = rank

        chosen_ids = {row[2].id for row in chosen}
        for score, _doc_id, doc, passage in candidates:
            if doc.id in chosen_ids:
                continue
            excluded.append(
                {
                    "source_id": doc.id,
                    "family": doc.kind,
                    "status": doc.status,
                    "version": doc.version,
                    "score": score,
                    "reason": "retired" if doc.status == "retired" else "below_top_k",
                    "matched_passage": passage[:240],
                    "request_index": request_index,
                }
            )

    # Dict insertion order follows retrieval-plan/intent order, which is more
    # useful to an operator than an alphabetical family sort.
    selected = list(selected_by_id.values())
    unresolved = []
    for query in queries:
        if not query["selected_ids"]:
            unresolved.append(
                {
                    "type": "knowledge_missing",
                    "family": query["family"],
                    "query": query["query"],
                    "supports": query["supports"],
                }
            )
    return {
        "selected": selected,
        "excluded": excluded,
        "queries": queries,
        "unresolved": unresolved,
    }
