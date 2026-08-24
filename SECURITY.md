# Security profile

This repository is a private demonstration, not a public customer-service system.

## Controls included

- Authentication is mandatory on non-loopback binds.
- Only five committed case IDs can start model runs.
- Arbitrary prompts and knowledge mutation are absent from the HTTP API.
- Request bodies, queued runs, concurrent model work, retained runs, and run frequency are bounded.
- Knowledge and transactional fixtures are read-only and synthetic.
- Model execution uses a read-only temporary directory and schema-constrained output.
- Unexpected server errors are logged server-side and returned as a generic client error.
- Security, no-cache, frame, referrer, permission, and content-type headers are emitted.
- OAuth and password material are ignored by Git and excluded from the Docker build context.

## Credential handling

Treat the Codex OAuth cache as a password. Never commit it, add it to an image, expose it to frontend code, paste it into issues, or include it in logs. Enter it directly into the target Railway account as a sealed variable and persist the refreshed cache on the service volume.

## Responsible disclosure

Do not place customer data or real production credentials in this demo. Report suspected credential exposure to the repository owner immediately and revoke the affected session before investigating further.
