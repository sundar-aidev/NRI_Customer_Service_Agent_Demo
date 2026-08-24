# NRI Query-to-Response Pipeline

- **Status:** Implemented locally and verified
- **Version:** 2.0
- **Date:** 24 August 2026
- **Audience:** Product, design, applied AI, engineering, evaluation, risk, and operations

## 1. Purpose and scope

This specification defines how the NRI demo should turn a marketplace-support query into a classified, grounded, calculated, cited, and appropriately human-gated response.

The implementation must make this statement true:

> Starting from the customer query and authorized conversation context, the system identifies every intent, selects the required Knowledge, Transactional, Calculation, and Human capabilities, retrieves the correct governed sources, applies deterministic decisions, generates a cited response, and exposes a stage-level evaluation trace.

The target flow is:

```text
Query and authorized context
  → classify
  → plan retrieval
  → retrieve Knowledge and Transactional evidence
  → apply deterministic rules and calculations
  → generate customer-safe draft
  → verify citations, facts, arithmetic, and authority
  → human review when required
```

### In scope

- The five fixed evaluation queries.
- Query-based multi-intent classification.
- Independent knowledge and transactional retrieval.
- Deterministic rules and calculations.
- LLM-generated customer responses grounded in retrieved evidence.
- Claim-level citations.
- Human review and approval states.
- Stage-level evaluation and audit traces.
- The Eval Bench and Data Layer user experience.

### Out of scope

- Executing real returns, refunds, replacements, coupons, or seller settlements.
- Giving an LLM unrestricted SQL, filesystem, or systems-of-record access.
- Treating the synthetic Company A knowledge pack as certified production policy.
- Using an LLM judge as the authority for arithmetic, source identity, policy status, safety, or approval.
- Claiming that five curated cases constitute a production benchmark.

## 2. Implemented state

### 2.1 What exists

| Capability | Status | Current behavior |
|---|---|---|
| Eval UI → live server | Wired | `Run case` invokes `POST /api/v2/runs` and polls the run trace. |
| Data Layer UI → backend | Wired | The UI loads `/api/knowledge` and `/api/records` from the same stores used at runtime. |
| Knowledge snapshot → pipeline | Wired | The hosted demo and runtime read the same immutable policy snapshot. |
| Transaction fixtures → pipeline | Wired | Typed adapters query authorized rows in `records/store.json`. |
| Model classification | Wired | The local ChatGPT-authenticated Codex client returns schema-constrained multi-intent output. |
| Query-driven source selection | Wired | The planner receives classified needs; K/T retrieval is not given gold source IDs. |
| Evidence → rules and model | Wired | Frozen document passages and exact record fields feed decisions and generation. |
| Deterministic decisioning | Wired | Eligibility, refund, stock feasibility, gaps, and authority are code-owned. |
| Runtime visible response | Wired | The main draft is generated for the current run and verified before display/send authority. |
| Retrieval and grounding evaluation | Wired | Isolated E1–E6 scoring evaluates classification, sources, decisions, response, and authority. |
| Human review | Wired | Human edit, approve, and reject actions are recorded and edited drafts are re-verified/re-scored. |

### 2.2 Current runtime

```text
One of five runtime-safe fixtures
  ├─ query and channel/locale
  ├─ authorized customer/order context
  └─ attachment certainty
       │
       ▼
Model-backed classification → retrieval plan
       │
       ├─ governed knowledge search
       └─ typed, scoped transaction tools
       │
       ▼
Frozen evidence → deterministic decisions/calculations
       │
       ▼
Grounded model draft → deterministic verification/one repair
       │
       ├─ isolated evaluator (fixed eval cases only)
       └─ human review when required
       │
       ▼
UI: current-run draft, trace, exact K/T evidence, and review state
```

Knowledge retrieval ranks the active local corpus by classified family plus lexical/concept relevance and preserves retired or unresolved candidates for audit. Transaction retrieval uses allow-listed adapters with customer/order scope and freshness checks. The frozen selected passages and fields—not source labels alone—feed deterministic decisions and the response model.

### 2.3 Verified behavior

Live subscription-OAuth runs against the current local API produced:

| Case | Runtime retrieval | Deterministic result | Generated response behavior |
|---|---|---|---|
| L1 | `KB-WAR-01`; no T lookup | 24-month small-appliance warranty | Cited policy answer generated at runtime |
| L2 | `SKU-AER500`; no K search | 0 available across 3 warehouses; no ETA | Cited live-stock answer generated at runtime |
| L3 | `KB-RET-01` + `ORD-10023998` | Within the delivery-based return window | Policy and order facts joined in one cited draft |
| L4 | `KB-REF-01` + `ORD-10024090` | Exact integer-cent refund: SGD 80.00 | Calculation output rendered verbatim |
| L5 | 7 K sources + 4 scoped T sources | D1–D5 in dependency order with open human gates | Useful remedy draft without inventing policy, stock, points, or goodwill |

### 2.4 Remaining production boundary

The private demo pipeline is complete for its five cases and negative tests. A real customer-facing deployment still requires tenant authentication, production K/T connectors, durable audit storage, policy-owner certification, action execution, monitoring, and a broader statistical evaluation set.

## 3. Target architecture

### 3.1 Ownership model

| Type | Owns | Runtime component | Must never do |
|---|---|---|---|
| **K — Knowledge** | Policy and governed guidance | Knowledge retrieval service | Treat retired, incomplete, or undefined policy as approved |
| **T — Transactional** | Customer/order/inventory/payment facts | Allow-listed transactional tools | Infer policy or access an unrelated customer |
| **C — Calculation** | Eligibility, proration, caps, feasibility | Deterministic rules engine | Delegate money arithmetic or certified decisions to the LLM |
| **D — Discretion** | Policy gaps, exceptions, goodwill, approval | Human workflow | Present a proposal as approved or completed |

The LLM classifies and writes. Controlled services fetch. Deterministic code decides and calculates. Humans own unresolved policy and discretion.

### 3.2 Pipeline stages

| Stage | Owner | Input | Required output | Safe failure |
|---|---|---|---|---|
| 1. Intake | Orchestration | Query, conversation, authenticated context, attachments | Immutable request envelope | Reject invalid or unauthorized context |
| 2. Classification | Model-backed classifier | Request envelope | Intents, entities, K/T/C/D, lookup needs, confidence, risk | Clarify or route to human |
| 3. Retrieval plan | Orchestration | Classification | Typed K searches and T tool calls | Mark blocked requirement |
| 4K. Knowledge retrieval | Retrieval service | Query, policy families, filters | Ranked current passages plus gaps/archive evidence | `knowledge_missing` or policy gap |
| 4T. Transaction retrieval | Typed tools | Authorized entity keys | Scoped records with freshness metadata | `transaction_unavailable` or clarification |
| 5. Evidence normalization | Orchestration | K and T results | Frozen evidence bundle, conflicts, unresolved needs | Preserve conflict; never flatten |
| 6. Rules/calculation | Rules engine | Evidence bundle | Decisions, calculations, dependencies, authority | `UNDEFINED` plus human owner |
| 7. Draft generation | LLM | Inquiry, evidence, decisions, authority | Customer-safe response with citations | No-answer draft or human review |
| 8. Verification | Deterministic validator | Draft and frozen run state | Grounding, numeric, citation, and authority verdict | Repair once, then human review |
| 9. Evaluation | Eval service | Runtime trace plus isolated gold | E1–E6 results | Mark stage failure explicitly |
| 10. Approval | Human workflow | Draft, evidence, decisions, verifier result | Approve, edit, or reject | Remain unsent |

### 3.3 Architecture guardrails

These four guardrails summarize the detailed requirements below:

1. **Isolation:** gold labels are evaluator-only; runtime source selection starts from the query and authorized context (`REQ-01`, `REQ-09`).
2. **Evidence integrity:** K and T remain separate retrieval paths, transactional access is typed and scoped, and generation receives actual passages and field values (`REQ-10` to `REQ-17`).
3. **Deterministic authority:** rules own eligibility and arithmetic; humans own unresolved policy and discretion; GenAI may classify, decompose, and phrase but never certify those outcomes (`REQ-18` to `REQ-24`).
4. **Truthful output:** every verifiable claim is grounded, lifecycle states remain distinct, and the visible response is runtime output rather than evaluator copy (`REQ-25` to `REQ-31`).

## 4. Canonical requirements

### 4.1 Intake and classification

**REQ-01 — Runtime/gold separation.** Split each eval case into a runtime fixture and a gold fixture. Only the scorer may load gold.

**REQ-02 — Authorized context.** Intake accepts the query, channel, locale, permitted customer/order context, and attachment observations. It assigns a stable `run_id`, `trace_id`, and source snapshot.

**REQ-03 — Attachment certainty.** An attachment may be `provided`, `machine_observed`, or `human_verified`. A filename or customer assertion alone does not establish a defect.

**REQ-04 — Multi-intent classification.** Classification returns primary and secondary intents, extracted entities, K/T/C/D requirements, lookup needs, decision needs, candidate autonomy, risk flags, missing information, and confidence.

**REQ-05 — Schema-constrained model output.** The demo uses a configured model-backed classifier with validated structured output. A deterministic classifier may remain as a clearly identified baseline or fallback.

**REQ-06 — Controlled taxonomy.** Intent, evidence need, lookup type, and autonomy values come from controlled enums. Free-text rationale is audit-only.

**REQ-07 — Complex decomposition.** A multi-part query creates decision-sized subproblems. L5 must create D1–D5.

**REQ-08 — Ambiguity handling.** Low confidence or ambiguous customer/order identity produces one minimal clarification or human review; it never silently selects a record.

### 4.2 Retrieval

**REQ-09 — Planner boundary.** Classification produces evidence needs; the retrieval planner converts them into typed K searches and T tool calls.

**REQ-10 — Parallel paths.** Run K and T retrieval in parallel when both are needed, and preserve which intent/decision each request supports.

**REQ-11 — Minimal access.** Do not retrieve unrelated policy families, orders, history, or customer data merely because they are available.

**REQ-12 — Knowledge search.** Select knowledge from the query and classified policy family using:

- hard filters for status, effective date, locale, and business scope;
- lexical matching for precise terms;
- semantic ranking for paraphrases;
- optional reranking for final top results.

**REQ-13 — Knowledge governance.** Only `current` documents can support an approved answer. Return `undefined`/`incomplete` documents as policy-gap evidence. Keep `retired` results for audit but exclude them from decisions.

**REQ-14 — Knowledge result contract.** Return source ID, title, family, version, effective date, status, owner, provenance, matched passages, retrieval method/score, and snapshot hash.

**REQ-15 — Transaction tools.** Initial allow-listed tools are:

- `get_customer_orders(customer_id)`;
- `get_order(order_id)`;
- `get_delivery(order_id)`;
- `get_inventory(sku_or_product, region)`;
- `get_payment_allocation(order_id)`;
- `get_loyalty_ledger(customer_id, order_id)`;
- `get_compensation_history(customer_id)`;
- `get_product_master(sku_or_product)`.

**REQ-16 — Transaction result contract.** Return the source system, record ID, selected fields, freshness, retrieval time, and access scope. Preserve missing, stale, ambiguous, and unavailable states.

**REQ-17 — Evidence bundle.** Normalize K and T results into one immutable bundle while retaining type, source, supporting intent/decision, conflicts, unresolved evidence, and policy gaps.

### 4.3 Rules, decisions, and authority

**REQ-18 — Deterministic ownership.** Eligibility, refund composition, coupon allocation, points restoration, caps, stock feasibility, and approval thresholds are deterministic functions.

**REQ-19 — Exact money.** Currency calculations use integer minor units and expose the input lines, operations, output amount, rule version, and evidence references.

**REQ-20 — Undefined policy.** Missing rule parameters produce `UNDEFINED`, the responsible policy owner, and `requires_human=true`. Generation cannot replace the result with an estimate.

**REQ-21 — Decision contract.** Every decision includes ID, question, owner, outcome, lifecycle state, evidence references, rule version, dependency IDs, and human requirement.

**REQ-22 — Authority owners.** Decision owners are `Rules`, `Orchestration`, or `Human`. Record GenAI separately as a classifier, proposer, or generator; it is never the authority for financial outcomes, policy precedence, or discretionary entitlement.

**REQ-23 — L5 dependency order.** D1 gates D2–D5; D2 fixes internal remedy ownership; D3 proposes the remedy path and inherits D4 authority; D4 controls money/tender restoration; D5 is discretionary and evaluated last.

**REQ-24 — Lifecycle language.** The UI and generated response must not describe `proposed` or `attempted` work as `approved` or `completed`.

### 4.4 Generation, verification, and review

**REQ-25 — Grounded generation.** Generate the visible draft only after evidence and deterministic decisions are frozen.

**REQ-26 — Generator input.** The LLM receives the inquiry, relevant conversation context, classification, frozen evidence, deterministic decisions, authority constraints, and style instructions—nothing from gold.

**REQ-27 — Response constraints.** The draft must:

- answer every classified intent or identify what remains unresolved;
- cite every policy, live fact, date, amount, and completed action;
- use deterministic calculation outputs verbatim;
- avoid unsupported promises, internal-only seller/funding detail, and private reasoning;
- use concise marketplace-chat language;
- remain a draft when human-owned decisions are open.

**REQ-28 — Deterministic verification.** Validate citation existence, exact values for money/date/stock/order facts, policy status, decision consistency, and execution language.

**REQ-29 — Repair policy.** One failed verification may trigger one constrained regeneration. A second failure routes to human review and cannot be sent.

**REQ-30 — Human review trigger.** Review is mandatory for policy gaps, discretionary goodwill, ambiguous identity, conflicting or missing evidence, always-human scenarios, authority thresholds, low classification confidence, or repeated verification failure.

**REQ-31 — Review package.** Show the draft, intents, retrieved evidence, calculations, open gaps, decision owners, and verifier output together. Record edits, approval/rejection, and reason.

## 5. Runtime and API contract

### 5.1 HTTP endpoints

Only `/healthz` is public. All application and API routes require reviewer authentication when hosted.

| Endpoint | Purpose |
|---|---|
| `GET /healthz` | Minimal Railway readiness probe |
| `GET /api/health` | Authenticated provider and runtime status |
| `GET /api/v2/cases` | Return the five runtime-safe fixtures |
| `POST /api/v2/runs` | Start a pipeline run for one allowed case ID |
| `GET /api/v2/runs/{run_id}` | Return current stage and completed artifacts |
| `POST /api/v2/runs/{run_id}/review` | Edit, approve, or reject a completed draft |
| `GET /api/knowledge` | Browse the read-only knowledge snapshot |
| `GET /api/records` | Browse the read-only synthetic records |

### 5.2 Start-run request

```json
{
  "case_id": "l3_return_eligible_join",
  "evaluation_mode": true
}
```

`case_id` identifies an allow-listed eval row. The server copies its runtime-safe fields into the pipeline and rejects arbitrary query/context fields. It never copies expected intents, K/T/C/D labels, source IDs, decisions, citations, or answer facts.

### 5.3 Canonical run result

```json
{
  "run_id": "run_03",
  "trace_id": "trace_03",
  "status": "awaiting_review",
  "active_stage": "approval",
  "source_snapshot": "snapshot_2026_08_24",
  "classification": {
    "primary_intent": "return_eligibility",
    "secondary_intents": [],
    "confidence": 0.97,
    "requirements": ["K", "T"],
    "entities": {
      "customer_id": "C2266",
      "order_id": "ORD-10023998"
    },
    "knowledge_families": ["returns_refunds"],
    "lookup_needs": ["delivery_status"],
    "decision_needs": ["return_eligibility"],
    "autonomy_candidate": "draft_only_human_review",
    "risk_flags": [],
    "missing_information": []
  },
  "retrieval_plan": {
    "knowledge_requests": [
      {
        "family": "returns_refunds",
        "query": "return window begins from delivery date"
      }
    ],
    "transaction_requests": [
      {
        "tool": "get_order",
        "arguments": {
          "order_id": "ORD-10023998"
        }
      }
    ]
  },
  "evidence": {
    "knowledge": [
      {
        "source_id": "KB-RET-01",
        "status": "current",
        "version": "v2026-03",
        "matched_passage": "The 30-day return window starts on delivery."
      }
    ],
    "transactions": [
      {
        "source_id": "ORD-10023998",
        "system": "OMS",
        "freshness": "fixture-live",
        "fields": {
          "status": "delivered",
          "delivered_days_ago": 1
        }
      }
    ],
    "unresolved": [],
    "policy_gaps": []
  },
  "decisions": [
    {
      "decision_id": "return_eligibility",
      "owner": "Rules",
      "outcome": "eligible",
      "state": "approved",
      "requires_human": false,
      "evidence_refs": ["KB-RET-01", "ORD-10023998"],
      "rule_version": "return_eligibility_v1",
      "depends_on": []
    }
  ],
  "draft": {
    "text": "Yes. Your order was delivered yesterday, so it is within the 30-day return window. [KB-RET-01] [ORD-10023998]",
    "citations": [
      {
        "source_id": "KB-RET-01",
        "claim": "30-day window starts from delivery"
      },
      {
        "source_id": "ORD-10023998",
        "claim": "delivered yesterday"
      }
    ],
    "answered_intents": ["return_eligibility"],
    "unanswered_intents": []
  },
  "verification": {
    "passed": true,
    "errors": [],
    "repair_count": 0
  },
  "authority": {
    "requires_human": true,
    "reason": "evaluation policy requires reviewed draft",
    "state": "awaiting_review"
  },
  "evaluation": {
    "E1": "pass",
    "E2": "pass",
    "E3": "pass",
    "E4": "pass",
    "E5": "pass",
    "E6": "reported_separately",
    "passed": true
  }
}
```

### 5.4 Run lifecycle

Keep overall lifecycle separate from pipeline progress:

| Field | Allowed values | Meaning |
|---|---|---|
| `status` | `queued`, `running`, `awaiting_review`, `completed`, `rejected`, `failed` | Overall run outcome |
| `active_stage` | `intake`, `classification`, `retrieval_planning`, `knowledge_retrieval`, `transaction_retrieval`, `evidence_normalization`, `decisioning`, `generation`, `verification`, `evaluation`, `approval`, `complete` | Current or last stage |

K and T retrieval may be active concurrently and should emit separate progress events. In evaluation mode, E1–E6 may be computed after verification while the draft remains `awaiting_review`. A run becomes `completed` only when no review is required or the required review has been approved. A rejected review sets `status=rejected` and never creates a send action.

The same immutable knowledge snapshot and record adapters serve both the pipeline and Data Layer UI so displayed and runtime evidence cannot drift.

## 6. Evaluation specification

### 6.1 Fixture separation

Replace the combined case file with:

```text
evals/runtime_cases.json
  case_id
  query
  permitted conversation context
  attachment observations

evals/gold_labels.json
  expected intents
  expected K/T/C/D
  expected knowledge source IDs
  expected transaction source IDs
  expected decisions/calculations
  expected authority
  required answer facts
```

Only the evaluation service may load `gold_labels.json`.

### 6.2 Stage scores

| Group | Stage | Required deterministic checks |
|---|---|---|
| **E1** | Classification | Intent-set match, K/T/C/D exact match, entities, lookup types, decision decomposition, autonomy candidate |
| **E2** | Retrieval | Knowledge Recall@k/Precision@k, primary rank, current version, exact record match, freshness, no cross-customer or unnecessary access |
| **E3** | Decisions | Exact outcome, exact integer-cent amount, rule version, evidence coverage, `UNDEFINED` handling, D1–D5 dependency order |
| **E4** | Response grounding | Citation resolution, claim coverage, numeric/date/stock equality, no unsupported fact or completion claim |
| **E5** | Authority and safety | Correct human gate, autonomy tier, no unsafe action, no send when approval is open |
| **E6** | Customer quality | Completeness, relevance, concision, empathy, marketplace-chat tone; optional blinded LLM judge |

A case passes only when E1–E5 pass and no critical safety invariant fails. E6 is reported separately unless the response is unusable or unsafe.

Run model-backed stages multiple times and report pass rate. Do not hide variance behind one successful sample.

### 6.3 Five-case gold matrix

The following values are evaluator-only.

| Level | Query summary | Expected intents | Requires | Expected K | Expected T | Decision/answer contract | Authority |
|---|---|---|---|---|---|---|---|
| L1 | Warranty duration for small appliances | `warranty_terms` | K | `KB-WAR-01` | None | 24 months from delivery; normal-use defects covered; misuse excluded | Auto-draft internal |
| L2 | Aeromix 500 stock | `stock_availability` | T | None | `SKU-AER500` | Zero stock across three warehouses; no confirmed ETA | Auto-draft internal |
| L3 | Return after delivery yesterday | `return_eligibility` | K + T | `KB-RET-01` | `ORD-10023998` | Within 30-day delivery-based window | Human-reviewed draft |
| L4 | Partial refund with 20% coupon | `partial_refund`, `coupon_proration` | K + T + C | `KB-REF-01` | `ORD-10024090` | SGD 100 − SGD 20 coupon allocation + SGD 0 shipping = **SGD 80** | Human-reviewed draft |
| L5 | Damaged sale item; return, replacement, refund, points, compensation | `defect_return`, `remedy_ownership`, `replacement`, `refund_composition`, `goodwill_compensation` | K + T + C + D | `KB-RET-01`, `KB-MKT-01`, `KB-PRE-01`, `KB-REF-01`, `KB-PTS-01`, `KB-GDW-01`, `KB-STK-01` | `ORD-10024120`, `SKU-AER500`, `PTS-LEDGER-C8891`, `HIST-C8891` | D1–D5 below | Human-owned at go-live |

### 6.4 L5 decision contract

| Decision | Evidence required | Outcome contract | Owner |
|---|---|---|---|
| **D1 Return eligibility** | Verified damage evidence, sale flag, seller/fulfilment, delivery, return policies | Policy precedence is not certified. Return acceptance requires verified defect plus human/certified precedence. Gates D2–D5. | Human at go-live |
| **D2 Remedy ownership** | Seller, fulfilment, merchant of record, marketplace policy | Customer remedy and seller settlement are separate. Keep funding allocation internal. | Human |
| **D3 Replacement remedy** | Same-SKU inventory, inbound date, line value, product attributes | Same SKU cannot ship now at stock zero. Offer a confirmed comparable in-stock alternative or refund; do not ask the customer to wait without a committed date. | Proposal; inherits D4 authority |
| **D4 Refund composition** | Tender split, coupon, points tranches/expiry, discount allocation | Use a certified restoration table. Do not invent treatment for expired points. | Human while policy incomplete |
| **D5 Goodwill** | Compensation history, values/reasons, fraud/risk state, goodwill policy | Discretionary; do not promise a coupon or amount. Evaluate last. | Human |

The L5 draft must acknowledge the damage, use verified facts only, avoid internal seller-versus-company detail, explain the immediate stock constraint, present available remedy choices, defer unresolved refund composition and goodwill appropriately, and ask only for the customer's remedy preference.

L5 may remain a fixed one-turn input for the demo. The meaningful interaction is human review/edit/approval of the generated draft. A clarification turn appears only when the runtime genuinely lacks an entity or evidence.

### 6.5 Required negative tests

- Gold source ID accidentally enters the classifier or retriever input.
- Knowledge-only query triggers an order lookup.
- Transaction-only query triggers irrelevant policy retrieval.
- Retired policy ranks above current policy.
- Current policies conflict.
- Wrong customer or wrong order is selected.
- Inventory is stale or unavailable.
- Required transactional entity is ambiguous.
- Rule parameter is undefined.
- LLM changes the deterministic refund amount.
- Draft contains a source-free live fact.
- Draft promises an unapproved or unexecuted action.
- Citation points to a source not present in the run evidence.
- Verification fails twice.

## 7. Product behavior

### 7.1 Eval Bench

Before a run:

- Display the fixed customer query.
- Keep expected sources and expected response hidden in normal demo mode.
- In evaluator mode, show expected K/T/C/D only as clearly labelled gold.
- Use `Run pipeline` or `Generate response` as the primary action.

During a run:

- Show Classification, Retrieval, Decisions, Draft, and Verification progress.
- Populate the evidence sidebar only from completed retrieval results.
- Distinguish loading, success, blocked, and failed stages.

After a run:

- Show the generated response as the primary draft.
- Open exact evidence from inline citations.
- Show a compact stage trace and E1–E6 results.
- Put the expected response in an evaluator-only comparison.
- Show review/edit/approve controls only when the authority result requires them.

Example trace:

```text
Classified   Return eligibility · K + T
Retrieved    KB-RET-01 · ORD-10023998
Decided      Eligible · delivered yesterday · 30-day window
Generated    2 cited claims
Verified     Grounding passed
Authority    Human-reviewed draft
```

### 7.2 Evidence sidebar

Keep the existing `Transactional` and `Knowledge` tabs. For each source show:

- why it was selected and which intent/decision it supports;
- retrieval rank or tool name;
- status, version, provenance, freshness, and source system;
- exact passages or fields used;
- response claims citing it;
- selected, excluded, stale, conflicting, or unresolved state.

Counts represent sources retrieved for the current run, not all sources authored for the case.

### 7.3 Data Layer

Knowledge Base:

- Search title, body, family, owner, and status.
- Expose version, effective date, provenance, and current/incomplete/undefined/retired state.
- Keep the hosted evidence browser read-only; policy experiments belong in a separate development environment.
- Link to runs that actually retrieved the document.

Live Data:

- Organize records as orders, deliveries, inventory, payments, loyalty, customer history, and products.
- Show source system and freshness.
- Link to runs that actually retrieved the record.
- Enforce customer scope; search must not expose unrelated records.

### 7.4 Visible states

```text
Ready · Classifying · Retrieving K · Retrieving T · Applying C
Generating · Verifying · Passed · Eval finding · Missing data
Policy gap · Conflicting evidence · Awaiting approval · Approved
Rejected · Source unavailable
```

Status must not rely on color alone. Tabs, citations, evidence rows, and review controls must be keyboard accessible and explicitly labelled.

## 8. Safety and operations

### 8.1 Data and model boundary

- Enforce tenant/customer scope outside the LLM.
- Return only fields required for the classified intent.
- Redact or tokenize sensitive values before prompting.
- Treat retrieved document and record text as untrusted evidence, never instructions.
- Retrieved content cannot alter tool permissions, rules, or authority thresholds.
- Log access decisions and tool calls.

### 8.2 Failure policy

| Failure | Behavior |
|---|---|
| Low classification confidence | One minimal clarification or human review |
| Multiple plausible orders | Ask/select from authorized candidates; never guess |
| Knowledge miss | Do not answer from general model knowledge |
| Retired document selected | Exclude it; continue with current sources or surface a miss |
| Conflicting policy | Preserve both sources; emit policy gap; require human |
| Transaction API unavailable | Do not assert live status |
| Stale inventory | Do not promise replacement |
| Undefined rule parameter | Return `UNDEFINED`; require policy owner/human |
| First draft-verification failure | Regenerate once with constrained feedback |
| Second verification failure | Human review; do not send |
| Missing execution proof | Remain `attempted` or `pending`, never `completed` |

### 8.3 Audit record

Persist or make replayable:

- run/trace IDs and source snapshot;
- query hash and authorized context IDs;
- classifier/generator model and prompt versions;
- classification and confidence;
- retrieval queries, tool calls, selected/excluded sources, versions, and freshness;
- frozen evidence bundle;
- rule versions, inputs, calculations, decisions, and owners;
- draft, citations, validator results, and repair count;
- authority gate and human edits/approval/rejection;
- execution proof if later implemented;
- E1–E6 results and stage latency.

### 8.4 Demo performance targets

| Stage | p95 target |
|---|---:|
| Classification | ≤ 1.5 s |
| Retrieval plan | ≤ 0.3 s |
| Parallel K/T retrieval | ≤ 1.5 s |
| Rules/calculation | ≤ 0.2 s |
| Draft generation | ≤ 4.0 s |
| Verification | ≤ 1.0 s |
| End-to-end non-human case | ≤ 7.0 s |

Rules and calculations must be reproducible from a frozen evidence snapshot. Log model, prompt, schema, and sampling versions so model-backed runs can be replayed and compared.

## 9. Implementation plan

### 9.1 Implemented modules

```text
demo/
  pipeline/
    schemas.py
    orchestrator.py
    classifier.py
    retrieval_planner.py
    knowledge_search.py
    transaction_tools.py
    evidence.py
    decisions.py
    generator.py
    verifier.py
    # trace emission is owned by orchestrator.py
  evals/
    runtime_cases.json
    gold_labels.json
    scorer_v2.py
  prompts/
    classifier_v1.md
    response_v1.md
    repair_v1.md
  rules/
    policy_rules.py
  knowledge/
  records/
  page/
  serve.py
```

### 9.2 Delivery sequence

| Phase | Deliverables | Exit gate | Status |
|---|---|---|---|
| **0. Truthful baseline** | Resolve L3 policy/gold mismatch and label provenance | Every gold answer is supported by governed demo evidence | Complete |
| **1. Classification** | Runtime/gold split, schemas, model classifier, E1, trace | Five cases classify without gold IDs | Complete |
| **2. Retrieval** | Governed K search, typed T tools, frozen evidence, E2 | Exact sources selected; wrong/stale/extra tests fail safely | Complete |
| **3. Decisions** | Evidence contract, integer cents, gaps, D1–D5, E3 | Outcomes match gold; undefined policy stays human-owned | Complete |
| **4. Generation** | OAuth provider, grounded prompts, citations, verifier/repair, E4/E6 | Runtime drafts are grounded and evidence-sensitive | Complete |
| **5. Product workflow** | Live draft, progress, E5, evidence tabs, review actions, failure tests | L5 is gated and all cases expose stage results | Complete |

The phases were delivered in this order so runtime generation was enabled only after source leakage was removed and retrieval could be scored independently.

## 10. Definition of done

The target pipeline is complete when:

1. Runtime components cannot read gold intent, source, decision, or answer labels.
2. All five queries produce the expected intent set and K/T/C/D requirements.
3. Retrieval independently selects the expected documents and records from the query and authorized context.
4. Rules and generation receive actual evidence values.
5. L4 deterministically returns exactly SGD 80.00.
6. L5 produces D1–D5 and retains all policy-gap/discretionary gates.
7. The visible response is generated at runtime and changes consistently when evidence changes.
8. Every factual claim, amount, date, stock state, and execution statement is verifiably cited.
9. The sidebar contains only evidence from the current run.
10. Classification, retrieval, decisions, grounding, authority, and response quality are reported separately.
11. Missing, stale, conflicting, or ambiguous evidence causes a safe non-answer, clarification, or review.
12. No proposed, unapproved, or unexecuted action is shown as completed.

### 10.1 Verification snapshot — 24 August 2026

- 26 deterministic pipeline, API, UI-contract, scope, and failure tests pass.
- Two consecutive five-case live runs using ChatGPT subscription OAuth passed E1–E5 with zero response repairs in every case.
- The L5 browser flow passed dynamic K/T retrieval, verification, evaluation, evidence-tab rendering, and human approval.
- Desktop and narrow Chrome captures show a full-viewport layout with the context workspace collapsed behind `View context` at narrow widths.
- `GET /api/health` reports `query_driven_v2`, `authenticated=true`, and `mode=chatgpt_subscription`.

## 11. Implementation decisions

Recommendations make the demo plan executable; owners may replace them with an explicit recorded decision.

| ID | Decision | Recommended demo default | Owner | Blocks |
|---|---|---|---|---|
| DEC-01 | Model topology/provider | Use one provider adapter with separate classifier, generator, and repair prompts; keep schemas provider-neutral | Applied AI | Phase 1 |
| DEC-02 | Knowledge search | Use governed family filters plus local lexical/concept ranking; add embeddings/reranking only if a larger corpus requires them | Applied AI | Phase 2 |
| DEC-03 | Transaction integration | Use typed local adapters over fixtures; design production connectors separately | Engineering | Production only |
| DEC-04 | Customer/session identity | Marketplace integration supplies authenticated customer ID and authorized active-order candidates | Product + Engineering | Phase 2 |
| DEC-05 | Confidence thresholds | Calibrate on the five cases plus negative tests; confidence never bypasses a mandatory human gate | Applied AI + Risk | Phases 1 and 5 |
| DEC-06 | Policy certification | Keep synthetic provenance visible; require named policy-owner approval before any production use | Operations + Risk | Production only |
| DEC-07 | L3 policy coverage | Keep the user-preferred query, but add a clearly synthetic general-return rule or change the gold to a clarification; do not treat the current defect-only clause as general coverage | Product + Evaluation | Phase 0 |
| DEC-08 | L5 response state | Show an unsent proposed draft before review; render send-ready copy only after D1, D4, and D5 are resolved or explicitly deferred by a human | Product + Risk | Phases 4 and 5 |
| DEC-09 | Approval surface | Keep approval inside the demo; treat external support-console integration as later work | Product | Phase 5 |

## 12. Sources of truth

Authority is concern-specific; do not use one artifact to override another outside its scope:

| Concern | Governing source |
|---|---|
| Current implementation behavior | Code plus `README.md` |
| Runtime eval query and authorized context | `evals/runtime_cases.json` |
| Evaluator-only expected intents, sources, decisions, and facts | `evals/gold_labels.json` |
| Policy content, status, version, and owner | Files under `knowledge/docs/` |
| L5 D1–D5 decision and authority model | Slide 2 decision register |
| Customer-facing wording and tone | `docs/EVAL_CASES.md` |

If these artifacts disagree, Phase 0 must reconcile the fixture and gold. Runtime code must not silently choose the most convenient interpretation.

- Current behavior and limitations: [`../README.md`](../README.md)
- Runtime cases: [`../evals/runtime_cases.json`](../evals/runtime_cases.json)
- Evaluator-only gold: [`../evals/gold_labels.json`](../evals/gold_labels.json)
- Knowledge resolver: [`../knowledge/retriever.py`](../knowledge/retriever.py)
- Transaction fixture resolver: [`../records/resolver.py`](../records/resolver.py)
- Orchestration: [`../pipeline/orchestrator.py`](../pipeline/orchestrator.py)
- Decisions: [`../pipeline/decisions.py`](../pipeline/decisions.py)
- Scoring: [`../evals/scorer_v2.py`](../evals/scorer_v2.py)
- Product UI: [`../page/template.html`](../page/template.html)
- Presentation-ready case copy: [`EVAL_CASES.md`](EVAL_CASES.md)
- Authoritative L5 register: external Slide 2 project artifact used to establish the case fixture
