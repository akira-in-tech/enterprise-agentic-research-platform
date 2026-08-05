# Security

## Implemented

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

- **CORS allowlist** — no CORS middleware is configured.
- **Authenticated sessions** — the platform uses pre-authentication
  `X-Tenant-ID` / `X-User-ID` headers, trusted directly rather than derived
  from an authenticated identity. See [data-model.md](data-model.md) for
  why the charter's `sessions` table is deliberately not added yet.
- **SSRF protection for user-provided URLs** — not yet audited/implemented
  as a dedicated control.
- **Prompt-injection-aware private document handling** — private documents
  are validated and tenant-isolated, but no dedicated prompt-injection
  mitigation exists on their content before it reaches an LLM.

Report these as open items, not as implemented controls, until each has a
corresponding test.
