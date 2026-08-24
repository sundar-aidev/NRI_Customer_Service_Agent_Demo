---
id: KB-STK-01
title: Out-of-stock remedy options
kind: fulfilment_remedies
version: v2026-01
effective_date: 2026-01-10
owner: Fulfilment Operations
status: current
provenance: DERIVED
provenance_note: brief - "the product is currently out of stock"
---

## Rule

When available stock for a SKU is **zero across all checked locations**, **no reshipment may be
promised**. A promise to reship the same item while stock reads zero is a commitment the
business cannot keep and must never be issued, automatically or otherwise.

The permitted responses when stock is zero are limited to exactly these three:

1. Offer an **alternative item**.
2. Offer a **refund**.
3. Offer a **restock notification** (notify the customer when the SKU is available again).

No other remedy may be offered in place of these three while stock remains at zero.

## Scope

Applies to any case where a reshipment, replacement, or exchange would require issuing the same
SKU and current available stock for that SKU is zero. It does not apply once stock is
replenished above zero, at which point ordinary reshipment rules resume.

## Related

- A goodwill gesture may accompany one of these three remedies, subject to the cap in
  `KB-GDW-01`.
- Refund arithmetic if the refund remedy is chosen: `KB-REF-01`.
