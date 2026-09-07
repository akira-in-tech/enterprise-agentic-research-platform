# Performance

This project's charter principle applies here as everywhere else: record
only numbers produced by a real, reproducible run, and never present a
measurement taken under one set of conditions as if it held under
another. The figures below come from one measurement pass against the
live AWS staging deployment on 2026-09-07, plus two local
micro-benchmarks. Research-workflow latency lives in
[evaluation.md](evaluation.md), not here, because it was measured against
the local stack with real providers.

## What was measured

A single pass on 2026-09-07, immediately before a planned
`terraform destroy` of the staging stack (AWS account 559987919619,
us-west-2). A manual RDS snapshot
(`evident-research-staging-final-20260907-0713`) was taken first and
retained; the billable stack was then destroyed, so these numbers
describe a deployment that no longer exists and are a historical
baseline, not a live SLA.

### Topology under test

```
CloudFront (PriceClass_100, HTTP/2 + HTTP/3)
  -> internet-facing ALB (security group admits only the CloudFront origin-facing prefix list)
  -> 1x ECS Fargate task: 512 CPU units (0.5 vCPU) / 1024 MB, three containers (api, mcp, frontend)
  -> RDS PostgreSQL 18.3, db.t4g.micro, single-AZ
  -> ElastiCache Valkey, cache.t4g.micro, one node
```

Application: FastAPI, SQLAlchemy async engine (default pool of 5 plus 10
overflow, `pool_pre_ping=True`), `redis.asyncio`. The running task was
five days old at measurement time, which matters for finding 1 below.

## Edge and read-path latency

Through CloudFront, sequential, connection warmed, n=100 per endpoint.

| Endpoint | p50 | p90 | p99 |
| --- | --- | --- | --- |
| `GET /api/health` (no I/O) | 32 ms | 56 ms | 134 ms |
| `GET /api/ready` (`SELECT 1` plus Redis `PING`) | 36 ms | 91 ms | 183 ms |
| `GET /api/providers` | 31 ms | 40 ms | 118 ms |
| `GET /` frontend (CloudFront cache hit) | 9 ms | 12 ms | 94 ms |

Cold-connection breakdown: DNS about 3 ms, TCP connect about 10 ms, TLS
established about 22 ms, time to first byte 55 to 75 ms. HTTP/2 was
negotiated; the response advertised HTTP/3 via `alt-svc`. The frontend
`index.html` is 547 bytes and was served from a CloudFront point of
presence, not the origin.

## Concurrency: compute-only path (`/api/health`)

300 requests per level through CloudFront.

| Concurrency | p50 | p99 | max | Throughput | Errors |
| --- | --- | --- | --- | --- | --- |
| 10 | 33 ms | 120 ms | 133 ms | 221 req/s | 0 |
| 25 | 36 ms | 174 ms | 176 ms | 466 req/s | 0 |
| 50 | 231 ms | 1317 ms | 1502 ms | 154 req/s | 0 |
| 100 | 516 ms | 2096 ms | 2133 ms | 134 req/s | 0 |

Throughput peaks near concurrency 25 at roughly 466 req/s, then collapses
as the 0.5 vCPU task saturates its CPU. No request was dropped at any
level: excess load queues and latency grows, but the error count stays
zero. CloudWatch for the burst window: ECS service CPU averaged 25
percent and peaked at 99.9 percent, memory held at 35 percent, RDS CPU
stayed under 8 percent, RDS connections stayed at or below 10, and
ElastiCache CPU was negligible.

## Concurrency: dependency-touching path (`/api/ready`)

`/api/ready` opens or reuses a PostgreSQL connection and pings Redis on
every call.

| Concurrency | HTTP 200 rate | 200-path p50 | Non-200 |
| --- | --- | --- | --- |
| 5 | 41% | 99 ms | HTTP 503 |
| 10 | 19% | 230 ms | HTTP 503 |
| 20 | 16% | 720 ms | HTTP 503 |

ALB `HTTPCode_Target_5XX` for the window was 1194 of 3425 requests. Two
causes compound here (findings 1 and 3). The endpoint fails closed: it
returns 503 rather than reporting "ready" when it cannot verify both
dependencies within its bounded client timeouts.

## Auth and DB-write path

Through CloudFront, sequential.

| Operation | min | p50 | p90 |
| --- | --- | --- | --- |
| `POST /auth/register` (Argon2id hash, PG insert, session) | 264 ms | 372 ms | 381 ms |
| `POST /auth/login` (Argon2id verify, session) | 210 ms | 284 ms | 341 ms |
| `GET /auth/me` (cookie to session lookup) | 40 ms | 49 ms | 77 ms |
| `GET /research-runs` (tenant-scoped list) | 38 ms | 58 ms | 127 ms |

Argon2id work factor dominates register and login and is deliberate.

## Rate limiting

Configured at 20 requests per 60 seconds, tenant-scoped, enforced on both
the synchronous and asynchronous research-submit endpoints
(`_enforce_rate_limit` in `app/api/research.py`). Successful responses
carry `X-RateLimit-Limit`, `X-RateLimit-Remaining`, and
`X-RateLimit-Reset`; an over-limit request returns 429 with
`Retry-After`. A clean 429-threshold measurement was not captured on this
pass: the probe was contaminated by finding 1 (stale DB credentials
returning intermittent 500s on submit) and by background retry storms
from an unreachable local provider saturating the 0.5 vCPU task. Re-run
after a rolling deployment to get a clean number.

## Local micro-benchmarks

Run on a developer machine, not AWS.

- **Redis result-cache hit read**: `RedisResearchResultCache.get()`,
  which is a Redis `GET` plus full Pydantic validation of a 50 KB cached
  report plus a provider check. Against a throwaway local Redis,
  n=2000: p50 0.31 ms, p90 0.69 ms, p99 1.09 ms, mean 0.40 ms. This is
  the read component only; the end-to-end cached HTTP response also
  carries session auth, idempotency, and rate-limit checks.
- **Top-20 evidence cap**: `select_top_evidence` caps the Analyst and
  Writer prompts to the 20 highest-scored sources. Rendering the real
  Writer evidence block with tiktoken, the cap cuts evidence tokens by
  60 percent on a 50-source pool and 71 percent on a 70-source pool
  (roughly 40K tokens down to 11K). The same cap raised independent
  source coverage from 80 percent to 100 percent in the published eval
  runs; see [evaluation.md](evaluation.md).

## Findings

1. **RDS-managed master password rotation is invisible to a running
   task.** The task started 2026-09-02; the RDS-managed secret rotated
   2026-09-06 under its 7-day schedule. ECS injects secrets only at task
   start, so new database connections fail authentication
   (`asyncpg.InvalidPasswordError`) while the connection pool's
   already-open connections keep working. Light traffic masks the
   problem; under load it surfaces as `/api/ready` 503s and submit 500s.
   Candidate fixes: an EventBridge rule on the Secrets Manager rotation
   event that triggers `aws ecs update-service --force-new-deployment`,
   or disabling automatic rotation for staging.

2. **The Anthropic key had no credit balance**, so every Claude call
   returned `400 invalid_request_error`. The Intent Router degraded to
   its deterministic rule-based fallback correctly; the Planner and
   Analyst structured calls then surfaced the failure as HTTP 500,
   because those nodes have no deterministic fallback. This matches the
   gap already recorded in [evaluation.md](evaluation.md).

3. **The 0.5 vCPU / 1 GB task, shared by three containers, is the single
   capacity constraint.** It saturates between concurrency 25 and 50. The
   data tier is heavily over-provisioned relative to it: RDS CPU under 8
   percent, ElastiCache negligible, under every load applied. The scaling
   lever is `application_desired_count` (horizontal) or a larger task
   size, not the database. No ECS autoscaling policy is configured.

4. **`/api/ready` fails closed.** Returning 503 rather than a false
   "ready" is the correct contract, but there is no fast-path or
   load-shedding for the health path itself, so dependency pressure
   becomes total readiness failure rather than degraded reporting.

5. **Healthy-path edge latency is strong.** Sub-40 ms p50 for API reads
   across the full CloudFront to ALB to Fargate path, 9 ms for the cached
   frontend, and error-free latency degradation under compute overload.

## Reproducing

The harness scripts are not committed (they are one-off measurement
tools, like the eval runner's `eval_runs/` artifacts). The method:

- Edge and concurrency: an async `httpx` client issuing warmed
  sequential batches and bounded-concurrency bursts against
  `/api/health`, `/api/ready`, `/api/providers`, and `/`.
- Auth: register a throwaway tenant, then time `login`, `me`, and the
  run list.
- Corroboration: `aws cloudwatch get-metric-statistics` for
  `AWS/ECS` CPU and memory, `AWS/ApplicationELB` `TargetResponseTime`
  and `HTTPCode_Target_5XX`, and `AWS/RDS` CPU and connections over the
  test window.
