# Product roadmap and verification gates

## v1 — Shipped in this package

- Single-owner workspace, login, and persistent agents/goals/tasks
- Real OpenAI-compatible text model integration by environment key
- CEO strategy generation with schema validation
- Human approval and rejection; manual plan fallback
- Specialist text deliverables with execution receipts
- Model usage records, preflight spend checks and budget UI
- SHA-256 chained audit events and an integrity verification endpoint
- Responsive dashboard, safe Docker compose, integration tests, CI workflow

## v1.1 — Planned, not implemented

- Per-agent and per-project budget policy engine with explicit reservations
- Provider-aware streaming of responses and robust job queue
- Multi-owner roles and delegated approval permissions
- Secure webhooks with signatures and replay protection
- Export of artifacts to a user-chosen repository via separate explicit approval

## v2 — Research and enterprise readiness

- Sandboxed external tools in network-isolated workers with allowlisted scopes
- Provenance-linked evidence, source verification, and evaluator agents
- Event sourcing and immutable external audit anchoring
- SSO, audit export, encrypted credential vault, team RBAC
- Benchmarked scale tests, disaster recovery, deployment health monitoring

## Release gates

1. Python syntax, JavaScript syntax, unit/integration tests pass.
2. Manual first-run owner setup, goal, approval, and task execution passes.
3. Live provider call is verified with a valid user-supplied key.
4. Security audit, cost check, backups, and TLS are configured for any public deployment.
5. Owner reviews release and explicitly approves GitHub push.

Passing the included unit tests is not evidence that gates 3–5 have passed.
