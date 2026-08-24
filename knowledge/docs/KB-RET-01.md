---
id: KB-RET-01
title: Company A common returns policy
kind: returns_refunds
version: v2026-03
effective_date: 2026-03-01
owner: Returns Policy Council
status: current
provenance: SYNTHETIC
provenance_note: defect exception derived from the brief; standard non-sale return rule authored for the L3 demo case
param_return_window_days: 30
---

## Rule

A standard **non-sale item** may be returned within **30 days of delivery**. This is the general
return rule used when a customer asks whether a recently delivered, non-sale order is still
inside its return window.

A **defective product** may also be returned within **30 days of delivery**, regardless of
whether the item was purchased during a sale and regardless of who sold it. This defect
exception can conflict with a marketplace seller's sale exclusion; that conflict is governed
separately by `KB-PRE-01`.

The window length is governed by the `return_window_days` parameter
(`param_return_window_days`, currently **30**) — changing that parameter changes the window
without changing this document's wording.

The return window is measured from the **delivery date on the order record**, never from the
order date.

## Scope

Applies to every item fulfilled from a Company A warehouse, including items sold by
marketplace sellers.

## Related

- Precedence against a conflicting seller policy: see `KB-PRE-01`.
- Marketplace responsibility split: see `KB-MKT-01`.
