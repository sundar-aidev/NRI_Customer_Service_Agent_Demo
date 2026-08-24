# KB Content Gap Register

Working tracker for knowledge the Company A support agent needs but does not yet have,
mirroring the shape of the inhouse gap register. Illustrative pack for the NRI case exercise —
this register exists so the pack demonstrates gap tracking, not only gap presence.

## How to close a gap

1. Get an approved rule from the named policy owner.
2. Author or amend the affected document(s) with the new rule, with correct provenance.
3. Re-run the retriever tests and the rules-layer tests to confirm no regression.
4. Mark the row **Closed** below and name the document that closed it.

## Gaps

Every row names the **section** of the pack the affected document is filed in, so the register
reads as *which part of the business is incomplete* rather than as a flat list. The sections
are the `kind` filing axis in `knowledge/retriever.py` (`KIND_ORDER`): 1 returns_refunds,
2 defects_warranties, 3 marketplace, 4 fulfilment_remedies, 5 goodwill, 6 open_decisions,
7 archive.

The section named is where the document **lives**, not where the gap is indexed. Section 6 is
a register, not a folder: `KB-PTS-01` is filed under returns and refunds, because that is what
an agent searches for, and section 6 merely points at it. Only `KB-PRE-01` — a precedence
question with no subject home of its own — actually lives in section 6.

Read down the Status column and the shape of the pack falls out: **the refund calculation
cannot complete** (G2, `KB-PTS-01`, filed in section 1) and **precedence has no rule at all**
(G1, `KB-PRE-01`, section 6). Every other subject is closed.

| Gap | Section | Subject | Affected document | Status | What would close it |
|-----|---------|---------|--------------------|--------|----------------------|
| G1 | 6 open_decisions | Precedence between a marketplace seller's non-returnable designation and Company A's common defect-return policy | KB-PRE-01 | Open | Assign an owner for cross-policy precedence; approve an ordering rule naming defect claims explicitly; re-adjudicate affected cases. |
| G2 | 1 returns_refunds | Refund treatment of loyalty points that expired after redemption but before the refund is issued | KB-PTS-01 | Open | An approved rule from the Loyalty Programme owner for expired-after-redemption tranches; re-run affected refund cases once approved. |
| G3 | 1 returns_refunds | Return window - length and whether it runs from purchase or delivery | KB-RET-01 | Closed | Closed by `KB-RET-01`: 30 days from delivery, superseding the 14-days-from-purchase rule in the retired `KB-RET-00`. |
| G4 | 5 goodwill | Goodwill compensation cap and whether a clean fraud history waives it | KB-GDW-01 | Closed | Closed by `KB-GDW-01`: cap of 2 grants per rolling 90 days; absence of a fraud flag does not waive the cap. |
| G5 | 4 fulfilment_remedies | Remedy options when a SKU is out of stock | KB-STK-01 | Closed | Closed by `KB-STK-01`: no reshipment promise at zero stock; remedies limited to an alternative item, a refund, or a restock notification. |

## Fields on an open gap

An open row is only actionable if the affected document says what it costs to leave it open.
Each document with `status: undefined` or `status: incomplete` therefore carries three
optional front-matter fields alongside its existing `owner`, and the open-decisions register
on the Knowledge tab renders all four as one labelled block per gap:

| Field | What it records |
|-------|------------------|
| `owner` | The policy owner who must rule. `UNASSIGNED` on `KB-PRE-01` is itself the finding. |
| `gap_consequence` | What cannot be done operationally while the question is open. |
| `gap_escalation` | Where a case routes today, before any rule exists. |
| `gap_closure` | What would close it. |

## Closure log

- Closed at pack authoring: G3 (`KB-RET-01`), G4 (`KB-GDW-01`), G5 (`KB-STK-01`).
- Still open: G1 (`KB-PRE-01`, lives in section 6 open_decisions), G2 (`KB-PTS-01`, lives in
  section 1 returns_refunds, indexed by section 6) — both route to a human until a policy
  owner approves a rule.
