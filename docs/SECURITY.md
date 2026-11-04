# Security model and limitations

## Present safeguards

- Owner authentication using salted `scrypt` password hashes (12+ characters).
- Random, server-stored, expiring HttpOnly cookies with SameSite=Lax.
- Anti-CSRF token required on authenticated mutations.
- No wildcard CORS, user HTML escaped in the UI, restrictive CSP and security headers.
- SQLite parameterized queries, WAL journal, immediate transactions for state changes.
- Explicit owner approval before materializing tasks.
- Explicit owner action before each task inference call.
- No automatic shell execution, Git push, publishing, payments, emails or browsing.
- Bounded planning schema, fixed role definitions, model timeouts, input size limit,
  password login rate limiting, and cost preflight.
- SHA-256 linked audit records with integrity checking endpoint.

## Not a substitute for an enterprise security review

- Single-owner design. No organization-level SSO/RBAC/multi-tenant isolation.
- Budgeting is **estimate-based** and provider-specific: it cannot enforce a
  hard ceiling on charges accrued during an in-flight request. Set provider-side
  billing limits independently.
- The audit log is tamper-*evident* for edits within the DB, not immutable:
  an attacker controlling the DB could recompute the entire chain. External
  signing / anchoring is required for higher assurance.
- The in-memory login throttle resets on service restart and is per-instance.
- Do not expose the HTTP service directly to the internet. Use TLS termination,
  authentication-aware ingress, backups, monitoring and controlled network access.
- SQLite is appropriate for small single-node installations, not a shared
  cluster-wide write database.
- AI responses are untrusted, may be wrong or contain prompt-injection content,
  and must be reviewed before use. Outputs are stored as plain text, not executed.
- Use a distinct environment secret for the model provider and rotate keys.
- A long model request occupies one server request thread. Use reverse-proxy
  limits and provider quotas to bound workloads.

## Operational checklist

1. Use a strong owner password, a private network, and HTTPS for public use.
2. Keep secrets out of the repository, database exports, and logs.
3. Enable model-provider usage limits to complement local estimates.
4. Back up the `APP_DB` volume regularly and test restoration.
5. Run `python -m pytest -q` before release; pin runtime versions.
6. Scan dependencies/container images and perform an independent audit.
7. Keep the AI agents' external actions disabled unless separately reviewed.
