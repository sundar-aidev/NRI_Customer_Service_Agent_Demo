# Task

Classify one marketplace customer-support inquiry. Do not answer the customer and do not select
document IDs or record IDs. Identify all distinct customer intents and the capability types the
runtime must use.

## Intent taxonomy

- `warranty_terms`: asks about warranty duration, scope, or exclusions.
- `stock_availability`: asks whether a named product is available or has a restock date.
- `return_eligibility`: asks whether a standard, non-defect order can be returned.
- `partial_refund`: asks for a refund on fewer than all order lines.
- `coupon_proration`: asks how a coupon changes a line-level refund.
- `defect_return`: reports damage/defect and asks to return the item.
- `remedy_ownership`: a marketplace sale requires deciding the internal remedy owner.
- `replacement`: asks to send, replace, reship, or exchange an item.
- `refund_composition`: asks how coupons, loyalty points, shipping, or tender types are restored.
- `goodwill_compensation`: asks for compensation, a goodwill credit, or a compensation coupon.

Use the most central intent as `primary_intent` and put every other applicable intent in
`secondary_intents`. Do not collapse a multi-part request into a generic intent.

## Capability requirements

- `K`: governed policy or knowledge is needed.
- `T`: a live order, inventory, payment, loyalty, or history record is needed.
- `C`: deterministic money calculation, proration, cap, or rule computation is needed.
- `D`: unresolved policy, exception, discretion, or human approval is needed.

Return only capabilities genuinely required by the inquiry. A standard return-window join is
K+T. Exact refund math is K+T+C. A complex damaged marketplace sale with refund tender ambiguity
and requested goodwill is K+T+C+D.

## Routing guidance

- Pure policy or stock facts may be `auto_draft_internal`.
- Return eligibility and refund amounts are `draft_only_human_review` for this demo.
- Policy conflicts, incomplete tender rules, or goodwill discretion are `always_human`.
- Authorized customer/order IDs in context are facts; copy them exactly and never invent IDs.
- Use empty strings/arrays when an entity or need is absent.
- Confidence measures classification confidence, not confidence that the requested action is allowed.
