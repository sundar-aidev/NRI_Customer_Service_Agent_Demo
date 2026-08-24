"""Resolve declared knowledge ids to governed Company A documents.

Stdlib only, no embeddings and no network. Cases declare the document ids they
depend on and this module returns those documents or fails loudly. A case that
silently grounds on nothing is the failure mode this module exists to prevent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

DOCS_DIR = Path(__file__).resolve().parent / "docs"

VALID_STATUS = {"current", "retired", "undefined", "incomplete"}
VALID_PROVENANCE = {"BRIEF", "DERIVED", "SYNTHETIC"}

# `kind` files a document by BUSINESS SUBJECT — the thing a support agent is
# looking up — while `status` says whether that document is healthy. They are
# orthogonal, and `kind` is descriptive metadata only: nothing in retrieval, the
# rules layer or scoring may branch on it.
#
# KIND_ORDER is the canonical presentation order. Sections 1-5 are live customer
# policy filed by subject; `open_decisions` (6) is the governance register; `archive`
# (7) is inactive policy kept so version selection stays testable. Any consumer that
# needs to order or label kinds reads it from here rather than restating the taxonomy.
#
# One document, one home. A document whose subject has a section lives in that
# section even when it carries a governance gap — `KB-PTS-01` is filed under
# returns and refunds, because that is what an agent searches for, and the
# open-decisions register merely *indexes* it. Only `KB-PRE-01`, a precedence
# question with no subject home of its own, actually lives in section 6.
KIND_ORDER = (
    "returns_refunds",
    "defects_warranties",
    "marketplace",
    "fulfilment_remedies",
    "goodwill",
    "open_decisions",
    "archive",
)

KIND_HEADING = {
    "returns_refunds": "Returns, Refunds and Payment Adjustments",
    "defects_warranties": "Defects and Warranties",
    "marketplace": "Marketplace Orders and Seller Responsibilities",
    "fulfilment_remedies": "Stock-outs, Replacements and Fulfilment Remedies",
    "goodwill": "Goodwill and Customer Compensation",
    "open_decisions": "Open Policy Decisions",
    "archive": "Policy Archive and Version History",
}

# The headings are self-explaining subjects, so the per-section line states what the
# section COVERS and who OWNS it rather than posing a question. Every owner named
# here is copied from the `owner` field of a document filed in that section.
KIND_BLURB = {
    "returns_refunds": "What a customer is owed when an order goes wrong, and how the amount is worked out. "
    "Owner: Returns Policy Council, Finance Operations, Loyalty Programme.",
    "defects_warranties": "How long a delivered product stays covered, and under which product category. "
    "Owner: Product Assurance.",
    "marketplace": "Who is answerable when the party that sold the item is not the party that shipped it. "
    "Owner: Marketplace Operations.",
    "fulfilment_remedies": "What may be offered when the item cannot be shipped again. "
    "Owner: Fulfilment Operations.",
    "goodwill": "Discretionary compensation, the cap on it, and who may approve past that cap. "
    "Owner: Customer Care Policy.",
    "open_decisions": "Policy questions with no approved answer, and where each case routes meanwhile. "
    "Owner: UNASSIGNED.",
    "archive": "Superseded policy, retained for audit history and version selection, never cited. "
    "Owner: Returns Policy Council.",
}

VALID_KIND = set(KIND_ORDER)

REQUIRED_FIELDS = (
    "id",
    "title",
    "kind",
    "version",
    "effective_date",
    "owner",
    "status",
    "provenance",
)

# Optional front matter, validated only when present. These are the fields the
# open-decisions register needs to be actionable rather than merely a list of
# unknowns: what breaks operationally while the question is open, where a case
# goes today, and what would close it. A document that carries a governance gap
# is expected to carry all three; a document with an answer carries none.
GAP_FIELDS = ("gap_consequence", "gap_escalation", "gap_closure")


class UnknownDocument(KeyError):
    """Raised when a case declares a knowledge id that does not exist."""


@dataclass(frozen=True)
class Document:
    id: str
    title: str
    kind: str
    version: str
    effective_date: str
    owner: str
    status: str
    provenance: str
    provenance_note: str
    body: str
    params: dict[str, str] = field(default_factory=dict, compare=False)
    gap_consequence: str = ""
    gap_escalation: str = ""
    gap_closure: str = ""

    @property
    def is_gap(self) -> bool:
        """True when the document records a governance gap instead of an answer."""
        return self.status in {"undefined", "incomplete"}

    @property
    def kind_heading(self) -> str:
        """The rendered heading of the section this document is filed under."""
        return KIND_HEADING[self.kind]

    @property
    def kind_blurb(self) -> str:
        """What this document's section covers, and who owns it."""
        return KIND_BLURB[self.kind]


def _parse(text: str, path: Path) -> Document:
    if not text.startswith("---\n"):
        raise ValueError(f"{path.name}: missing front matter")
    _, front, body = text.split("---\n", 2)
    meta: dict[str, str] = {}
    for line in front.splitlines():
        if not line.strip():
            continue
        key, _, value = line.partition(":")
        meta[key.strip()] = value.strip()
    missing = [f for f in REQUIRED_FIELDS if f not in meta]
    if missing:
        raise ValueError(f"{path.name}: missing front-matter fields {missing}")
    if meta["status"] not in VALID_STATUS:
        raise ValueError(f"{path.name}: status {meta['status']!r} not in {sorted(VALID_STATUS)}")
    if meta["provenance"] not in VALID_PROVENANCE:
        raise ValueError(
            f"{path.name}: provenance {meta['provenance']!r} not in {sorted(VALID_PROVENANCE)}"
        )
    if meta["kind"] not in VALID_KIND:
        raise ValueError(f"{path.name}: kind {meta['kind']!r} not in {list(KIND_ORDER)}")
    # Optional, so absence is fine; present-but-blank is not, because a register
    # row reading "escalation: (blank)" is worse than no row at all.
    for gap_field in GAP_FIELDS:
        if gap_field in meta and not meta[gap_field].strip():
            raise ValueError(f"{path.name}: {gap_field} is present but empty")
    params = {k[len("param_") :]: v for k, v in meta.items() if k.startswith("param_")}
    return Document(
        id=meta["id"],
        title=meta["title"],
        kind=meta["kind"],
        version=meta["version"],
        effective_date=meta["effective_date"],
        owner=meta["owner"],
        status=meta["status"],
        provenance=meta["provenance"],
        provenance_note=meta.get("provenance_note", ""),
        body=body.strip(),
        params=params,
        gap_consequence=meta.get("gap_consequence", "").strip(),
        gap_escalation=meta.get("gap_escalation", "").strip(),
        gap_closure=meta.get("gap_closure", "").strip(),
    )


def load_all(docs_dir: Path = DOCS_DIR) -> dict[str, Document]:
    docs: dict[str, Document] = {}
    for path in sorted(docs_dir.glob("*.md")):
        doc = _parse(path.read_text(encoding="utf-8"), path)
        if doc.id in docs:
            raise ValueError(f"duplicate document id {doc.id} in {path.name}")
        docs[doc.id] = doc
    return docs


def resolve(ids: Sequence[str], docs: dict[str, Document] | None = None) -> list[Document]:
    docs = load_all() if docs is None else docs
    out: list[Document] = []
    for doc_id in ids:
        if doc_id not in docs:
            raise UnknownDocument(f"no such knowledge document: {doc_id}")
        out.append(docs[doc_id])
    return out
