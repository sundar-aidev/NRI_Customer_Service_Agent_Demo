# Railway deployment — private reviewer demo

This profile is for a short-lived, access-controlled demonstration using one ChatGPT subscription OAuth session. It is not the authentication design for a public or multi-tenant product.

## What the Railway account owner must provide

1. Access to the Railway workspace and the target project/environment.
2. Permission for Railway to read the GitHub repository.
3. A reviewer username and a demo password of at least 6 characters.
4. The Codex OAuth cache entered directly into Railway as a sealed variable.
5. A single Railway volume mounted at `/data`.
6. Approval to create one public Railway domain after the service is healthy.

Do not send the OAuth cache, password, or Railway token through chat or commit them to Git.

## Required Railway variables

| Variable | Required | Description |
|---|---:|---|
| `NRI_DEMO_USERNAME` | Yes | Shared reviewer username |
| `NRI_DEMO_PASSWORD` | Yes | Reviewer password; minimum 6 characters |
| `NRI_REQUIRE_AUTH` | Yes | Set to `true` |
| `CODEX_AUTH_JSON_B64` | First boot | Base64-encoded Codex `auth.json`; seal this variable |
| `NRI_STATE_ROOT` | No | Defaults to `/data`, the documented volume mount |
| `NRI_CODEX_MODEL` | No | Leave empty to use the subscription default |
| `NRI_MODEL_TIMEOUT` | No | Defaults to `300` seconds |
| `NRI_RUN_WORKERS` | No | Defaults to `2` |
| `NRI_RUN_LIMIT` | No | Defaults to `60` runs per reviewer IP per hour |

Railway injects `PORT`; do not set it manually.

## Prepare the OAuth value safely

First confirm that the local Codex CLI uses ChatGPT authentication:

```bash
codex login status
```

Confirm that `~/.codex/auth.json` exists without printing it:

```bash
test -s ~/.codex/auth.json && echo "OAuth cache ready"
```

On macOS, copy its base64 representation directly to the clipboard without printing the credential:

```bash
base64 < ~/.codex/auth.json | tr -d '\n' | pbcopy
```

Paste that value directly into the Railway variable named `CODEX_AUTH_JSON_B64`, mark/seal the variable, and clear the clipboard afterward. If Codex stores credentials in the system keychain rather than `auth.json`, switch the Codex credential store to file and sign in again before this step.

## Create the service

1. In the intended Railway account, create or select a project.
2. Add a service from the GitHub repository `sundar-aidev/NRI_Customer_Service_Agent_Demo`.
3. Select branch `main` and keep the repository root as the service root.
4. Railway will detect the root `Dockerfile` and `railway.json`.
5. Add the required variables above.
6. Attach a volume at `/data`. The entrypoint uses `/data/codex/auth.json` so refreshed credentials survive restarts.
7. Keep the service at exactly one replica. The demo intentionally keeps run/review state in memory.
8. Deploy and wait for `/healthz` to report healthy.
9. Generate a Railway public domain and open it in a private browser window.
10. Confirm that the browser requests credentials before rendering the interface.

## Acceptance checks

- `GET /healthz` returns `200` without revealing provider details.
- The application root returns `401` without reviewer credentials.
- `/api/health` reports `authenticated: true` after login.
- Each of the five cases can run once.
- An arbitrary-query request is rejected with `400`.
- Knowledge mutation routes return `404`.
- A restart preserves Codex authentication through the `/data` volume.
- Only one replica is configured.

## After the review

1. Remove the Railway public domain or delete the service.
2. Delete the `CODEX_AUTH_JSON_B64` variable.
3. Remove the persistent volume if the demo is finished.
4. Run `codex logout` locally if the copied OAuth session should be revoked.
5. Rotate the reviewer password before any future demo.
