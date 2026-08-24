---
id: KB-PRE-01
title: Precedence between seller policy and Company A common policy
kind: open_decisions
version: none
effective_date: none
owner: UNASSIGNED
status: undefined
provenance: BRIEF
provenance_note: brief - "precedence is undefined in the current state"
gap_consequence: No automated decision may be issued on a precedence conflict; a defective sale item sold by a marketplace seller cannot be adjudicated at all.
gap_escalation: Human review, with no policy owner assigned to take the decision - the escalation ends in a queue rather than at a desk.
gap_closure: Assign an owner for cross-policy precedence, approve an ordering rule naming defect claims explicitly, then re-adjudicate the affected cases.
param_precedence: undefined
---

## Status: UNDEFINED

There is no approved rule stating which policy prevails when a marketplace seller's policy
and Company A's common policy conflict. This is governed by the `precedence` parameter
(`param_precedence`), which takes one of three values: `undefined` (current — routes to a
human), `company_a_wins` (Company A's common returns policy prevails), or `seller_wins` (the
seller's non-returnable designation prevails). Setting the parameter to either resolved value
closes this gap and lets the decision be issued automatically.

The conflict is live and reachable today: a seller may mark sale items non-returnable
(`KB-MKT-01`) while Company A allows returns for defective products (`KB-RET-01`). A defective
sale item sold by a marketplace seller satisfies both, and they disagree.

## Consequence

Any case reaching this document routes to a human. No automated decision may be issued on a
precedence conflict until a policy owner is assigned and a rule is approved.

## What would close this gap

1. Assign an owner for cross-policy precedence.
2. Approve an ordering rule, with defect claims named explicitly.
3. Re-adjudicate the affected cases in the golden dataset under the approved rule.
