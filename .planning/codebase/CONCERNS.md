# Codebase Concerns

**Analysis Date:** 2026-03-14

## Tech Debt

**No Test Coverage:**
- Issue: Zero application-level tests across entire codebase (no .test.ts, .spec.ts, or .test.py files in src directories)
- Files: All source files under `src/`, `app/api/`, `agents/src/`, `mobile_frontend/src/`
- Impact: Regressions ship silently. Critical paths (payment processing, agent management, database operations) have no safety net.
- Fix approach: Establish test baseline for critical paths. Start with unit tests for `agents/src/shared/database_postgres.py`, `app/api/marketplace/execute/route.ts`, and Stripe payment endpoints. Add vitest/Jest configuration and CI integration.

**Fire-and-Forget Webhooks Without Retry/DLQ:**
- Issue: Webhook delivery to developer endpoints uses `.catch(err => console.error())` with no persistence or queue
- Files: `app/api/marketplace/execute/route.ts:58-70`, `app/api/marketplace/external/execute/route.ts:128-155`
- Impact: Failed webhook deliveries are logged but never retried. Developers won't know jobs completed if their server is briefly down.
- Fix approach: Implement webhook retry queue (Bull/RabbitMQ) with exponential backoff and DLQ fallback.

**Graceful Degradation Hides Misconfiguration:**
- Issue: Missing optional services (database, Qdrant, incident.io, Anthropic) fall back silently with `except Exception: pass` and generic no-op functions
- Files: `agents/src/butler/tools.py:23-50`, `agents/butler_api.py:185-238`
- Impact: If DATABASE_URL is missing, the system runs but drops all persistence silently. If ANTHROPIC_API_KEY is missing, Butler Agent is disabled but requests don't fail fast.
- Fix approach: Distinguish between optional vs. required services. Required services should fail fast at startup with clear error messages. Optional services can degrade gracefully but should emit metrics/warnings.

## Known Bugs

**Hardcoded Configuration Constants Scattered Across Codebase:**
- Symptoms: Multiple hardcoded addresses, values, and configurations replicated in different files (e.g., BUTLER_ADDRESS, USDC_ADDRESS in `mobile_frontend/src/components/VoiceAgent.tsx:43-48` vs. env var fallbacks)
- Files: `mobile_frontend/src/components/VoiceAgent.tsx:43-48`, `agents/src/butler/tools.py`, various API routes
- Trigger: Creating a new deployment environment or updating addresses requires changes to multiple unrelated files
- Workaround: Create environment-specific configuration files that are sourced by all modules

**SQL Injection Risk in Dynamic Query Building:**
- Symptoms: Manual SQL string concatenation in `agents/src/shared/database_postgres.py` for building WHERE clauses
- Files: `agents/src/shared/database_postgres.py:219-223`, `632-635`
- Trigger: If user input ever flows into the dynamic column/condition builders
- Workaround: None currently. The code is parameterized but future developers may skip that step when adding new queries.
- Fix approach: Use asyncpg's built-in query builders or migrate to an async ORM (SQLAlchemy, Tortoise ORM) that enforces parameterization.

**Type Safety Gaps in API Handlers:**
- Symptoms: `err: any` in error handlers, loose JSON schema validation with `z.unknown()` for complex nested proofs
- Files: `mobile_frontend/app/api/stripe/create-payment-intent/route.ts:62`, `app/api/marketplace/external/execute/route.ts:18`
- Trigger: Unexpected error shapes or malformed proofs crash handlers with vague errors
- Fix approach: Replace `any` with proper error types. Use discriminated unions for proof shapes.

**Unvalidated Job Status Transitions:**
- Symptoms: Job status can be set to any string value without validation of valid state transitions
- Files: `app/api/marketplace/execute/route.ts:30-33`, `agents/src/shared/database_postgres.py:265-289`
- Trigger: Invalid status values corrupt job state machine
- Fix approach: Create JobStatus enum, validate transitions before update (e.g., only "assigned" → "completed", not "open" → "completed")

## Security Considerations

**Webhook Signature Verification Only on Some Endpoints:**
- Risk: Some webhook handlers verify HMAC signatures (`app/api/marketplace/external/execute/route.ts:27-50`), others do not
- Files: `app/api/marketplace/execute/route.ts` (no signature verification), `app/api/webhooks/incident-io/route.ts` (no signature verification)
- Current mitigation: Auth key checking for `/execute` endpoint, but not for incident.io webhook
- Recommendations: Require HMAC signatures on ALL external webhook handlers. Add rate limiting on incident.io webhook. Use middleware to enforce signature verification globally.

**API Keys Stored Without Encryption:**
- Risk: Agent API keys stored in database; whether encrypted depends on the schema
- Files: `prisma/schema.prisma:40-42` (apiKey, apiKeyHash fields defined but encryption status unclear)
- Current mitigation: apiKeyHash field exists, suggesting hashing is intended
- Recommendations: Enforce encryption for all sensitive fields. Use sealed-box encryption (e.g., libsodium) with server-side key rotation. Add field-level encryption at the ORM layer.

**Cross-Site Request Forgery (CSRF) Not Visible:**
- Risk: No CSRF token middleware found in Next.js API routes
- Files: All `app/api/` routes accept POST without explicit CSRF validation
- Current mitigation: Potentially relying on SameSite cookie attribute, but not confirmed in code
- Recommendations: Add explicit CSRF token validation to all state-modifying endpoints. Use `csrf-csrf` package or Next.js auth middleware.

**Environment Variables Exposed in Error Messages:**
- Risk: Unredacted error logs may leak secrets
- Files: All files using `console.error(err)` with network/database errors
- Current mitigation: None visible
- Recommendations: Implement error sanitizer that strips secrets from error messages before logging. Use structured logging with redaction rules (Pino's `redact` option).

**No Rate Limiting on Stripe Payment Endpoint:**
- Risk: `/api/stripe/create-payment-intent` can be called without limits
- Files: `mobile_frontend/app/api/stripe/create-payment-intent/route.ts`
- Current mitigation: None visible
- Recommendations: Add per-user rate limiting (e.g., 5 requests per minute). Use `next-rate-limit` or auth-aware rate limiting middleware.

## Performance Bottlenecks

**N+1 Queries in Job List Fetch:**
- Problem: Listing marketplace jobs fetches job rows, but reputation/stats queries may be called per job
- Files: `agents/src/shared/database_postgres.py:298-310` (list_jobs), `app/api/marketplace/execute/route.ts:30` (update per job)
- Cause: No batch loading or eager loading of relationships
- Improvement path: Use JOIN queries to fetch jobs + stats in one query. Add database indexes on `jobId`, `status`, `createdAt`. Implement caching layer (Redis) for frequently accessed job lists.

**Fire-and-Forget Reputation Updates Without Batching:**
- Problem: Every job completion triggers async reputation upsert, each with individual DB queries
- Files: `app/api/marketplace/external/execute/route.ts:120-155`
- Cause: IIFE-wrapped async function called for each job without batch accumulation
- Improvement path: Collect reputation updates in a queue, batch process every 10 seconds. Add indexes on `agentId`. Consider eventual consistency (publish to message queue, consume batches).

**No Connection Pooling Configuration Limits:**
- Problem: asyncpg pool created with default max_size=5, may throttle under concurrent load
- Files: `agents/butler_api.py:201` (pool created but no tuning visible)
- Cause: No documented load test or sizing guidance
- Improvement path: Profile concurrent job count, set `max_size` to 2x expected concurrency. Add pool.getSize() metrics. Monitor queue wait times.

**Full JSON Parsing on Every JSONB Update:**
- Problem: JSONB fields round-tripped through `json.dumps()/json.loads()` on every upsert for normalization
- Files: `agents/src/shared/database_postgres.py:44-58`
- Cause: Normalizing non-JSON-native types (datetime, Decimal) requires full serialization
- Improvement path: Use database-side JSON functions for updates (PostgreSQL `jsonb_set`, `jsonb_merge_recurse`). Only deserialize when needed client-side.

**No Pagination on Worker Agent List:**
- Problem: `list_worker_agents` returns up to 100 agents in single query; no cursor-based pagination
- Files: `agents/src/shared/database_postgres.py:612-636`
- Cause: API could return large result sets for endpoints listing workers
- Improvement path: Implement cursor-based pagination. Add LIMIT clause support. Cache frequently accessed agent lists.

## Fragile Areas

**Butler Agent Initialization Chain with Silent Failures:**
- Files: `agents/butler_api.py:175-290`
- Why fragile: Multiple optional services (database, Qdrant, incident.io, Anthropic, Solana contracts) initialized in sequence. If any step fails, subsequent steps may assume it succeeded and use None values.
- Safe modification: Add explicit None checks after each service init. Use type system (Optional[X]) to surface None values. Add circuit breaker to disable Butler if critical service (Anthropic) is unavailable.
- Test coverage: No tests for initialization scenarios.

**Marketplace Job State Machine:**
- Files: `app/api/marketplace/execute/route.ts`, `agents/src/shared/database_postgres.py` (job creation/update)
- Why fragile: Status transitions not validated. No timestamp checks for expiration. Race conditions possible if multiple agents simultaneously update same job.
- Safe modification: Create explicit state transition validator. Add database constraints (CHECK status IN (...)). Use database-level locks or CTE for atomic updates.
- Test coverage: No tests for concurrent job updates.

**Webhook Delivery Pattern:**
- Files: `app/api/marketplace/execute/route.ts:57-70`, `app/api/marketplace/external/execute/route.ts`
- Why fragile: Fire-and-forget fetch with bare .catch(). If developer's webhook URL is dead, silently fails. No retry, no DLQ.
- Safe modification: Extract webhook delivery to separate service. Implement exponential backoff. Add persistence layer (webhook_attempts table). Add observability (metrics for success/failure rates).
- Test coverage: No tests.

**Database Pool Lifecycle:**
- Files: `agents/butler_api.py:177-204`, `agents/src/shared/database_postgres.py:107-129`
- Why fragile: Pool created in lifespan context manager but used in route handlers. If pool is closed or connection fails, handlers crash with cryptic asyncpg exceptions.
- Safe modification: Add healthcheck endpoint that validates pool. Implement connection retry logic with backoff. Add circuit breaker to reject requests if pool is exhausted.
- Test coverage: No tests.

**Stripe and Solana Integration Without Dual-Write Safety:**
- Files: `mobile_frontend/app/api/stripe/create-payment-intent/route.ts`, `agents/butler_api.py` (payment release)
- Why fragile: Creating Stripe intent and funding Solana escrow are separate operations. If second operation fails, Stripe charge processed but escrow not funded.
- Safe modification: Implement saga pattern (Stripe → record pending → Solana → confirm). Add compensation logic (refund Stripe if Solana fails). Add idempotency keys.
- Test coverage: No tests.

## Scaling Limits

**In-Memory Marketplace (JobBoard):**
- Current capacity: Limited by Node.js heap (typically 2GB default)
- Limit: Once in-memory job list exceeds available heap, process crashes or GC pauses increase
- Scaling path: Migrate JobBoard to persistent store (PostgreSQL already available). Implement pagination/filtering at database layer.

**Single asyncpg Pool for All Database Operations:**
- Current capacity: max_size=5 connections (hardcoded)
- Limit: Concurrent requests > 5 queue up. Under high load, connection acquisition times out.
- Scaling path: Increase max_size based on expected concurrent load. Consider connection pooler middleware (PgBouncer). Add connection pool metrics.

**Webhooks Processed Synchronously:**
- Current capacity: One webhook delivery per HTTP request, blocking until response
- Limit: If developer's webhook endpoint is slow (5s response), marketplace endpoint is blocked for 5s
- Scaling path: Offload webhooks to background queue (Bull, RabbitMQ). Return 202 immediately.

**Reputation Calculations Done Per-Request:**
- Current capacity: Each request computes new reputation average
- Limit: Complex calculations (rolling averages, failure type histograms) under high job completion rate become bottleneck
- Scaling path: Pre-aggregate reputation in batch jobs. Cache reputation scores. Use materialized views in database.

## Dependencies at Risk

**Stripe API Version Pinning:**
- Risk: Stripe API hardcoded to `2026-01-28.clover` (non-standard version name)
- Files: `mobile_frontend/app/api/stripe/create-payment-intent/route.ts:6`
- Impact: If this version is deprecated, payment creation breaks without warning
- Migration plan: Use stable Stripe API version (e.g., `2023-10-16`). Document rationale for custom version. Set up deprecation alerts.

**Elevenlabs Integration Patches:**
- Risk: `patch-package` applied to `@elevenlabs/react` during build
- Files: `mobile_frontend/package.json:8`, `mobile_frontend/scripts/patch-elevenlabs.js` (presumably exists)
- Impact: NPM updates may undo patches. Build depends on patch-package execution.
- Migration plan: Fork ElevenLabs repo if patches are critical. Document required patches and why. Contribute back to upstream if possible.

**Hardcoded Prisma Schema Assumptions:**
- Risk: Schema assumes specific column names/types. If database schema drifts, Prisma client breaks.
- Files: `prisma/schema.prisma`
- Impact: Manual database migrations not captured in Prisma schema cause type mismatches
- Migration plan: Enforce schema-as-code. Use `prisma migrate` for all changes. Add pre-deploy schema validation.

## Missing Critical Features

**No Observability/Monitoring:**
- Problem: No structured logging, metrics, or tracing visible
- Blocks: Cannot debug production issues. No alerting for degraded services.
- Solution: Add OpenTelemetry instrumentation (Pino for logging, Prometheus for metrics, Jaeger for traces). Set up monitoring dashboards and alerts.

**No Idempotency Keys:**
- Problem: Stripe payments and Solana transactions lack idempotency tracking
- Blocks: Network retries may cause double-charges or double-funding
- Solution: Add idempotency key tracking table. Hash request payload + user + endpoint, reject duplicates within 24h window.

**No Dead Letter Queue for Failed Jobs:**
- Problem: Failed marketplace jobs, data requests, or agent updates are logged but not retried
- Blocks: Cannot recover from transient failures without manual intervention
- Solution: Implement persistent job queue with exponential backoff. Auto-retry on transient errors (network, timeout). Manual review for persistent failures.

**No Rate Limiting on Public Endpoints:**
- Problem: `/api/agents`, `/api/marketplace`, Stripe payment endpoints have no rate limits
- Blocks: Bot abuse, DDoS vulnerability
- Solution: Add per-IP/per-user rate limiting. Use Redis-backed sliding window counter. Return 429 on limit exceeded.

**No Audit Trail for Admin Actions:**
- Problem: No logs for agent creation, payment release, job cancellation
- Blocks: Cannot investigate fraud or mistakes
- Solution: Log all admin/payment-affecting actions with user, timestamp, changes. Store in immutable audit table.

## Test Coverage Gaps

**Stripe Payment Endpoint Untested:**
- What's not tested: Payment intent creation, amount validation, currency conversion, metadata handling, error cases
- Files: `mobile_frontend/app/api/stripe/create-payment-intent/route.ts`
- Risk: Payment calculation logic (cents conversion, USDC decimals) could silently compute wrong amounts
- Priority: High

**Marketplace Job Execution Flow Untested:**
- What's not tested: Job assignment, status transitions, webhook delivery, reputation updates, escrow release
- Files: `app/api/marketplace/execute/route.ts`, `app/api/marketplace/external/execute/route.ts`
- Risk: Job execution flow is core to platform; any regression breaks agent payouts
- Priority: High

**Database Connection Pool Untested:**
- What's not tested: Pool exhaustion, connection timeout, reconnection after failure, concurrent access
- Files: `agents/src/shared/database_postgres.py:107-129`
- Risk: Production database failures could cascade
- Priority: High

**Authentication & Authorization Untested:**
- What's not tested: API key validation, webhook signature verification, agent assignment checks
- Files: `app/lib/auth.ts`, `app/api/marketplace/execute/route.ts:25`
- Risk: Unauthorized access to sensitive operations
- Priority: Critical

**Agent Initialization Untested:**
- What's not tested: Graceful degradation when services missing, service initialization order, circuit breaker logic
- Files: `agents/butler_api.py:175-290`
- Risk: Silent failures in production if external services become unavailable
- Priority: High

**JSONB Serialization Untested:**
- What's not tested: Complex nested structures, datetime handling, Decimal normalization, round-trip consistency
- Files: `agents/src/shared/database_postgres.py:44-76`
- Risk: Data corruption or loss when complex objects stored/retrieved from database
- Priority: Medium

---

*Concerns audit: 2026-03-14*
