# NRI Customer Service Agent Demo

A private, five-case evaluation product for demonstrating how a customer-service agent combines governed knowledge, scoped transactional records, deterministic decisions, and human judgment.

```text
fixed customer query + authorized context
  → model classification
  → typed K/T retrieval
  → deterministic rules and calculations
  → grounded response draft
  → deterministic verification
  → isolated evaluation
  → human review when required
```

The visible response, citations, evidence workspace, and pipeline trace are produced from the current run. Gold labels are loaded only by the evaluator.

## Evaluation ladder

| Level | Case | Requires | Demonstrates |
|---|---|---|---|
| L1 | Warranty duration | K | Policy retrieval without an order lookup |
| L2 | Aeromix stock check | T | Fresh inventory lookup without policy retrieval |
| L3 | Return eligibility | K + T | Return policy joined to the authenticated delivery record |
| L4 | Partial refund | K + T + C | Exact integer-cent coupon proration producing SGD 80.00 |
| L5 | Damaged sale item | K + T + C + D | Dependent decisions, policy gaps, remedy feasibility, and human approval |

`K` is governed knowledge, `T` is scoped transactional data, `C` is deterministic calculation/rules, and `D` is human discretion.

## Hosted-demo boundary

The hosted application is intentionally constrained:

- only the five committed case IDs are accepted by the backend;
- arbitrary customer prompts are rejected;
- knowledge and transactional fixtures are read-only;
- the application requires HTTP Basic authentication whenever it binds beyond localhost;
- model runs are rate-limited, queued through a bounded worker pool, and retained only temporarily;
- the public Railway healthcheck exposes no case or credential information.

The fixtures are synthetic. This demo does not execute refunds, returns, replacements, coupons, or other customer actions.

## Subscription OAuth

Classification and response generation use the ChatGPT-authenticated Codex CLI. No OpenAI API key is required.

Locally, authenticate once and confirm the session:

```bash
codex login
codex login status
```

`pipeline/model_provider.py` invokes `codex exec --ephemeral` with a read-only sandbox and schema-constrained output. Credential storage and refresh remain owned by Codex. Never commit `auth.json` or place its contents in application code.

For Railway, the production entrypoint restores the Codex authentication cache from the sealed `CODEX_AUTH_JSON_B64` variable only when a persistent cache does not already exist. See [Railway deployment](docs/RAILWAY_DEPLOYMENT.md).

## Run locally

Requirements: Python 3.11+ and a ChatGPT-authenticated Codex CLI.

```bash
./scripts/start-local.sh
```

Then open <http://127.0.0.1:8765/>.

Run one or all live cases from the CLI:

```bash
python3 -B run_cases.py --case l5_nri_sample
python3 -B run_cases.py --all --parallel 2
```

## Build and test

The application has no Python package dependencies. The deterministic suite uses a schema-compatible model stub and does not consume subscription usage.

```bash
./scripts/check.sh
```

The suite covers the five E1–E5 paths, runtime/gold separation, unnecessary retrieval, retired policy exclusion, cross-customer access, stale and ambiguous inventory, attachment certainty, exact refund arithmetic, ordered L5 decisions, verification failure, API authentication, body limits, fixed-case enforcement, and human review.

## API surface

All routes except `/healthz` require demo credentials when hosted.

| Endpoint | Purpose |
|---|---|
| `GET /healthz` | Minimal Railway readiness probe |
| `GET /api/health` | Authenticated provider and runtime status |
| `GET /api/v2/cases` | The five runtime-safe case inputs |
| `POST /api/v2/runs` | Start a run for an allowed case ID |
| `GET /api/v2/runs/{run_id}` | Poll observable trace and artifacts |
| `POST /api/v2/runs/{run_id}/review` | Edit, approve, or reject a generated draft |
| `GET /api/knowledge` | Browse the read-only knowledge snapshot |
| `GET /api/records` | Browse the synthetic system-of-record tables |

## Repository structure

```text
.
├── pipeline/                 classification, retrieval, decisions, generation, verification
├── evals/                    runtime-safe inputs, isolated gold labels, evaluator
├── knowledge/                governed policy documents and retriever
├── records/                  synthetic transactional fixtures and resolver
├── prompts/                  classifier, response, and repair prompts
├── page/                     product HTML and CSS source
├── tests/                    deterministic pipeline, API, UI, and security tests
├── scripts/                  local, production, and validation entrypoints
├── docs/                     pipeline specification, cases, and deployment guide
├── app_data.py               shared read-only data serialization
├── serve.py                  authenticated asynchronous HTTP application
├── run_cases.py              live subscription-OAuth command-line runner
├── build.py                  self-contained frontend build
├── Dockerfile                pinned Railway container
└── railway.json              Railway health and restart configuration
```

The detailed architecture and trust boundaries are in [docs/PIPELINE_SPEC.md](docs/PIPELINE_SPEC.md). Presentation-ready case wording is in [docs/EVAL_CASES.md](docs/EVAL_CASES.md).

## Limitations

- The policy corpus and records are synthetic demonstration fixtures.
- Five curated cases are not a statistically representative production benchmark.
- Run and review state is intentionally in memory and resets on redeploy.
- The OAuth-backed runner is appropriate only for this access-controlled demonstration, not a public or multi-tenant application.
- Real connectors, action execution, durable audit storage, and certified policy ownership are outside this repository.
