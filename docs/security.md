# Security

## Implemented

- **Authentication** — email+password registration and login. Passwords are
  hashed with Argon2id (`app/services/auth/passwords.py`); sessions are
  server-side and durable (a `sessions` table storing a SHA-256 hash of a
  `secrets.token_urlsafe(32)` token, never the raw token), delivered as an
  `httpOnly`, `SameSite=Lax` cookie (`Secure` outside development) rather
  than a JS-readable token. Every route derives `tenant_id`/`user_id` from
  the verified session via `get_current_session`
  (`app/api/dependencies.py`) — no client-supplied header is trusted for
  identity anymore. Login against an unknown email still pays the same
  Argon2 cost as a real one (a dummy-hash verify), so response timing
  doesn't reveal whether an address is registered. Self-service
  registration always creates a new tenant, so `User.email` is globally
  unique (not just per-tenant) to keep login unambiguous. Deliberately out
  of scope for this pass: email verification, password-reset-via-email,
  MFA, and multi-tenant-per-email support.
- **CORS allowlist** — `CORSMiddleware` is added only when
  `CORS_ALLOWED_ORIGINS` is configured (empty by default, so same-origin
  deployments add no attack surface); `allow_credentials=True` so the
  session cookie can be sent cross-origin to the Vite dev server, which
  requires an explicit origin list rather than `*` (enforced by browsers,
  and `parse_cors_allowed_origins` never returns a wildcard).
- **Tenant isolation** — every PostgreSQL query and Milvus search/delete is
  scoped by `tenant_id`; cross-tenant lookups return not-found rather than
  leaking existence.
- **Secrets outside source control** — configuration via environment
  variables / `.env` (gitignored); AWS Secrets Manager in the staging
  Terraform.
- **Document validation** — media-type and size limits, filename
  sanitization, deterministic content-hash deduplication
  (`app/services/knowledge/`).
- **Rate limiting** — tenant-scoped, fails closed under Redis outage.
- **Audit trail** — append-only `research_audit_events`, including
  `human_review_requested` events recorded through the MCP
  `request_human_review` tool.
- **Least-privilege AWS IAM** — staging Terraform scopes ECS task access
  narrowly (S3 objects, Bedrock embeddings); GitHub OIDC deployment
  identity has exact repository/environment trust with reviewed inline
  policies (see the root README's AWS section for what has actually been
  applied vs. only planned).
- **Encryption** — RDS, ElastiCache/Valkey, and S3 are declared encrypted
  in Terraform; S3 also blocks all public access and enforces HTTPS-only
  access.
- **No raw credentials in logs** — provider clients keep SDK types and
  secrets behind application interfaces; the correlation-ID log filter
  only ever injects a UUID or a validated, printable client-supplied ID.

## Not yet implemented

- **Email verification, password reset, and MFA** — deliberately deferred
  MVP scope for the authentication system above.
- **SSRF protection for user-provided URLs** — not yet audited/implemented
  as a dedicated control.
- **Prompt-injection-aware private document handling** — private documents
  are validated and tenant-isolated, but no dedicated prompt-injection
  mitigation exists on their content before it reaches an LLM.

Report these as open items, not as implemented controls, until each has a
corresponding test.
