---
id: KB-REF-01
title: Refund composition - coupons, points and shipping
kind: returns_refunds
version: v2026-01
effective_date: 2026-01-10
owner: Finance Operations
status: current
provenance: SYNTHETIC
provenance_note: authored; the brief states no refund arithmetic
param_shipping_refundable_on_partial: false
---

## Rule

A refund is composed from three elements, each governed by its own rule:

1. **Order-level coupon.** A coupon applied at order level is **apportioned across order lines
   by line value** (each line's share of the coupon equals its share of the order subtotal). A
   line-level coupon is not apportioned; it applies only to the line it was issued against.
2. **Shipping.** Shipping is refunded **only when the return is a full return** of every item on
   the order. A partial return never refunds shipping, even if the returned line was the only
   one requiring the higher shipping tier. This is governed by the
   `shipping_refundable_on_partial` parameter (`param_shipping_refundable_on_partial`, currently
   **false**); setting it to true would refund shipping on a partial return as well.
3. **Loyalty points.** Points redeemed as part of the original payment are refunded per the
   ledger rules in `KB-PTS-01`, not under this document.

## Arithmetic

All refund amounts are **computed in integer cents**. No step in the calculation may introduce
a fractional cent; apportionment is truncated, not rounded, to keep the sum of line refunds
within the coupon total.

## Scope

Applies to any refund calculation on an order with a coupon, a partial or full return, or a
points-funded line. It does not define eligibility to return in the first place; that is
`KB-RET-01`.

## Related

- Return eligibility: `KB-RET-01`.
- Loyalty points ledger and expiry: `KB-PTS-01`.
