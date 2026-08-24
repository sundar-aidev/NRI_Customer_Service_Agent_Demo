"""Company A transactional record store.

Deterministic fixtures standing in for OMS, WMS, the loyalty ledger and customer
history. Offline: no database, no network. The inhouse pipeline decides *that* a
lookup is needed; this module decides what a declared record can satisfy.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Sequence

STORE_PATH = Path(__file__).resolve().parent / "store.json"

LOOKUP_CLASS_BY_TYPE = {
    "order": "order_status",
    "sku": "stock_online",
    "points_ledger": "promotion_validity",
    "compensation_history": "order_status",
}


class UnknownRecord(KeyError):
    """Raised when a case declares a record id that does not exist."""


def load_store(path: Path = STORE_PATH) -> dict[str, dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def _require(record_ids: Sequence[str], store: dict[str, dict]) -> list[dict]:
    out = []
    for rid in record_ids:
        if rid not in store:
            raise UnknownRecord(f"no such record: {rid}")
        out.append(store[rid])
    return out


def lookup_classes_for(record_ids: Sequence[str], store: dict[str, dict]) -> list[str]:
    """Lookup classes the given records can satisfy, deduplicated and sorted."""
    classes = {LOOKUP_CLASS_BY_TYPE[rec["type"]] for rec in _require(record_ids, store)}
    return sorted(classes)


def records_for(record_ids: Sequence[str], store: dict[str, dict]) -> dict[str, dict]:
    _require(record_ids, store)
    return {rid: store[rid] for rid in record_ids}
