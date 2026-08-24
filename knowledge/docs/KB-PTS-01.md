---
id: KB-PTS-01
title: Loyalty points redemption and expiry
kind: returns_refunds
version: v2025-11
effective_date: 2025-11-01
owner: Loyalty Programme
status: incomplete
provenance: DERIVED
provenance_note: brief - "some of the redeemed points have already expired"
gap_consequence: No automated refund amount may be computed for an order carrying a tranche that expired after redemption but before the refund.
gap_escalation: Human review, with the Loyalty Programme as the named owner who must rule on the treatment.
gap_closure: An approved rule from the Loyalty Programme for expired-after-redemption tranches, then re-running the affected refund cases.
param_expired_points_treatment: undefined
---

## Rule

When a customer redeems loyalty points against an order, the redemption is recorded on the
**points ledger** as a tranche carrying its own **expiry date**, distinct from the order date.
The ledger is the system of record for how many points were redeemed, when, and when that
tranche expires; it is authoritative over any balance the customer reports from memory.

## Status: INCOMPLETE

This document does not define what happens when a redeemed tranche **expires after redemption
but before a refund is issued against that order**. Refunding cash in place of expired points,
reissuing points, or some blended treatment are all plausible outcomes, and none is approved.
This is governed by the `expired_points_treatment` parameter (`param_expired_points_treatment`),
which takes one of three values: `undefined` (current — routes to a human), `forfeit` (expired
points are forfeit; the refund is computed without them), or `refund_cash` (the expired
tranches' value is paid back as cash on top of the refund).

**Any case reaching this gap routes to a human.** No automated refund amount may be computed
for an order carrying an expired-after-redemption tranche until this is resolved.

## Scope

Applies to any order where the original payment included loyalty points, whether or not those
points have since expired.

## Related

- Refund composition (coupons, points, shipping): `KB-REF-01`.
- What would close this gap: an approved rule for expired-after-redemption tranches from the
  Loyalty Programme owner, then re-adjudication of affected cases.
