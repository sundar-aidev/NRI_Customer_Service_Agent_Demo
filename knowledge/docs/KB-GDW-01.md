---
id: KB-GDW-01
title: Goodwill compensation limits
kind: goodwill
version: v2026-01
effective_date: 2026-01-10
owner: Customer Care Policy
status: current
provenance: DERIVED
provenance_note: brief - "has received compensation twice within the past 90 days"
param_goodwill_cap_per_90_days: 2
---

## Rule

Goodwill compensation (a discretionary coupon, credit, or similar gesture) is capped at
**2 grants per rolling 90 days per customer**, governed by the `goodwill_cap_per_90_days`
parameter (`param_goodwill_cap_per_90_days`, currently **2**). The window is rolling, counted
back from the date of the current request, not a fixed calendar quarter.

A **third or later request** within that rolling 90-day window **requires human approval**; it
may not be auto-granted regardless of the reason for the request.

The **absence of a fraud flag on the customer's history does not waive the cap.** A clean
history is not grounds for an automatic exception — it only means fraud is not the reason for
escalation; the grant-count cap still applies on its own terms.

## Scope

Applies to any discretionary compensation decision for a customer, independent of the intent
category (delayed order, defect, stock-out, or other) that prompted the request.

## Related

- Out-of-stock remedies that may include a goodwill gesture: `KB-STK-01`.
- This cap is a decision boundary, not a refund calculation; refund arithmetic for a return is
  `KB-REF-01`.
