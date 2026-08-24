# Selected Eval Cases for the Demo

This walkthrough uses five representative cases, one from each level of the K/T/C/D evaluation ladder.

> **Note:** The case bank stores gold routes, autonomy tiers, source requirements, and decision outcomes—not literal gold-response prose. The expected answers below are presentation-ready customer responses derived from the fixtures and the Slide 2 decision register.

## Case overview

| Level | Case | Requires | Why show it |
|---|---|---|---|
| L1 | `l1_warranty_category` | **K** | Cleanly demonstrates a category-level policy answer that requires no transactional lookup. |
| L2 | `l2_stock_check` | **T** | Clean pass demonstrating correct use of live transactional data. |
| L3 | `l3_return_eligible_join` | **K + T** | Joins return policy with the delivery record; also reveals excessive human gating. |
| L4 | `l4_partial_refund_proration` | **K + T + C** | Deterministic coupon calculation produces the exact SGD 80.00 refund without model arithmetic. |
| L5 | `l5_nri_sample` | **K + T + C + D** | Decomposes the NRI scenario into eligibility, reshipment, refund, compensation, and human approval. |

**Legend:** **K** = Knowledge · **T** = Transactional data · **C** = Calculation/rules · **D** = Human discretion

---

## L1 — Retrieve from knowledge

- **Case:** `l1_warranty_category`
- **Requires:** K
- **Why show it:** It cleanly demonstrates a category-level policy answer that requires no transactional lookup.

### Customer query

> What's the warranty on small kitchen appliances—one year or two?

### Expected answer

> Small kitchen appliances have a 24-month warranty from the date of delivery for defects arising during normal use. Damage caused by misuse is not covered.

**Expected handling:** Retrieve `KB-WAR-01` and answer directly; no transactional lookup is required.

---

## L2 — Look up transactional data

- **Case:** `l2_stock_check`
- **Requires:** T
- **Why show it:** It is a clean pass demonstrating the correct use of live transactional data.

### Customer query

> Is the Aeromix 500 blender back in stock?

### Expected answer

> No. The Aeromix 500 blender is currently out of stock across all checked locations, and there is no confirmed restock date at the moment.

**Expected handling:** Look up `stock_online`, then answer directly from the verified stock record.

---

## L3 — Join knowledge and transactional data

- **Case:** `l3_return_eligible_join`
- **Requires:** K + T
- **Why show it:** It joins the return policy with the delivery record and reveals excessive human gating by the agent.

### Customer query

> Can I still return this? It arrived yesterday.

### Expected answer

> Yes. Your order was delivered yesterday, so it is within the 30-day return window. The return period starts from the delivery date, not the order date.

**Expected handling:** Join `KB-RET-01` with order `ORD-10023998`; prepare a direct answer for human review.

---

## L4 — Apply a deterministic calculation

- **Case:** `l4_partial_refund_proration`
- **Requires:** K + T + C
- **Why show it:** It demonstrates that exact money calculations are performed by deterministic rules rather than model arithmetic.

### Customer query

> I'm returning the SGD 100 wireless earbuds from my two-item order. I used a 20% coupon—how much do I get back?

### Expected answer

> For the SGD 100.00 wireless earbuds, your refund is SGD 80.00. The allocated portion of the 20% coupon is SGD 20.00. Because this is a partial return, the SGD 8.00 shipping charge is not refunded.

**Expected handling:** Retrieve order `ORD-10024090`, apply the coupon-proration and partial-shipping rules, and prepare the result for human review.

**Calculation trace:**

```text
Wireless earbuds                         SGD 100.00
Allocated 20% coupon                    -SGD  20.00
Refundable item value                    SGD  80.00
Shipping refunded on a partial return    SGD   0.00
Final refund                             SGD  80.00
```

---

## L5 — Judge a complex, multi-part request

- **Case:** `l5_nri_sample`
- **Requires:** K + T + C + D
- **Why show it:** It decomposes the NRI scenario into eligibility, reshipment, refund, compensation, and human approval.

### Customer query

> The product I received yesterday was damaged, and I've attached photos. It was purchased during a sale. Can I still return it? I used both a coupon and loyalty points. I would like the same product to be sent immediately. In addition to a refund, I would also like a compensation coupon.

### Expected answer

> Hi [Customer Name],
>
> I'm sorry your product arrived damaged. We've verified your order and photos, and we can proceed with the return despite the item being purchased during a sale.
>
> The same product is currently out of stock, so we cannot send an immediate replacement. You can choose either:
>
> - a refund; or
> - an exchange for a comparable in-stock product of similar value, subject to availability and confirmation of any price difference.
>
> Because your purchase used a coupon and loyalty points, we'll confirm the exact refund breakdown before processing it.
>
> Your request for a compensation coupon has also been submitted for review.
>
> Please let us know whether you prefer a refund or an exchange, and we'll send the return instructions.
>
> Kind regards,<br>
> Company A Customer Support

**UI status:** `Draft generated · Human approval required before sending`

### Expected decision breakdown

| Decision | Expected outcome | Owner |
|---|---|---|
| D1 · Return eligibility | **Conditional:** verify the defect; the proposed rank puts the defect policy above the sale exclusion, but a human owns the decision until that rank is certified | Human at go-live |
| D2 · Remedy ownership | **Split:** customer resolution and seller settlement are separate; Company A fronts the remedy only where guarantee and funding permit | Human at go-live and target |
| D3 · Replacement remedy | Same-SKU replacement is impossible at stock zero; offer a refund or propose a comparable in-stock item, subject to availability, price difference, and human confirmation | Proposal; chosen remedy inherits D4 authority |
| D4 · Refund composition | Cash, coupon, and points restoration cannot be confirmed until a restoration decision table is certified; GenAI does not perform the arithmetic | Human at go-live |
| D5 · Goodwill compensation | **Discretionary:** history is assembled, but no amount or entitlement can be derived without a certified rule | Human at go-live and target |
| Overall response | One owner issues one conditional response; attempted actions are not treated as completed without system proof | Human-controlled at go-live |

---

## Presentation notes

1. **Use SGD, not a generic currency marker.** The transactional fixtures identify the order currency as SGD.
2. **Label the L1 warranty policy as illustrative.** `KB-WAR-01` is a synthetic category-level policy created for the demo; the NRI brief does not supply warranty periods.
3. **The L4 query is intentionally clarified for presentation.** The stored case says only “one of the two items”; the presentation version identifies the SGD 100.00 wireless earbuds so the SGD 80.00 answer is fully supported.
4. **Preload verified evidence for L5.** The UI should show that the order and attached damage photos were verified before generating a draft that says the return can proceed.
5. **A comparable exchange is a proposed remedy, not an automatic entitlement.** Availability, equivalence, and any price difference must be checked and approved before it is promised to the customer.
6. **The Slide 2 register is authoritative for L5.** The runnable demo adds synthetic or derived rules so its fixtures can produce deterministic outcomes. Those assumptions must not be presented as certified Company A policy. All five L5 decisions remain human-controlled at go-live, and the generated response is a draft for human approval.
