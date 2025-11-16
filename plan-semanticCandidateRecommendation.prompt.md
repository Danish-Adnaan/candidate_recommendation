## Plan: Semantic Candidate Recommendation Backend

Concise FastAPI + MongoDB Atlas system to generate/store embeddings for candidates, serve vector similarity search for job descriptions, and log optional feedback. Emphasis on correct embedding dimension/model alignment, async non-blocking updates, sub-second filtered vector search at ~10k documents, resilient error handling, and future extensibility (multi-vector, personalization). Below are the focused implementation steps (logic only, no code) aligned to your prompt.

### Steps
1. Define data schemas (`app/models/candidate.py`, `feedback.py`, `job_description.py`) with embedding metadata (vector, model, dimensions, status, timestamps).
2. Create embedding service logic (`app/services/embedding.py`): input text assembly (skills + experience + education), dimension validation, retries, caching by JD hash.
3. Implement candidate CRUD & async embedding workflow (`app/services/candidate.py`, `tasks/queue.py`): insert/update sets `embedding_status=pending`, enqueue generation, update atomic on success/failure.
4. Build one-time backfill process (`scripts/backfill_embeddings.py`, `tasks/backfill.py`): batched fetch, concurrent embedding calls, bulk updates, error marking, idempotent skips.
5. Implement job description search route (`app/routes/search.py`, `app/services/search.py`): request validation, JD embedding cache, Mongo vector search with metadata filters, lean projection, latency metrics.
6. Add feedback logging route (`app/routes/feedback.py`, `app/services/feedback.py`): validate candidate & JD hash, store feedback + optional result snapshot, enforce compound uniqueness.
7. Integrate observability & resilience (`logging.py`, `metrics.py`, `middleware/correlation_id.py`, `exceptions.py`): structured logs, correlation IDs, Prometheus counters/histograms, classified error handling.
8. Optimize performance & index setup (`scripts/create_vector_index.py`): ensure correct model dimension, secondary filter indexes, connection pooling, response projection trimming.
9. Add testing strategy scaffolds (`tests/unit/*`, `tests/integration/*`): mock OpenAI, deterministic vector fixtures, search ordering assertions, feedback persistence tests.
10. Clarify model/dimension decision & migration path (`config.py`, embedding_version usage); resolve small vs large model trade-off before implementation start.

### Further Considerations
1. Embedding model choice: Use large (3072 dims, richer) vs dual-field migration?
2. Background task backend: Use an async in-process worker (FastAPI-only) with atomic claim via `find_one_and_update`, `lock_owner`, `lock_acquired_at`, and a stale-lock TTL; bounded concurrency via `asyncio.Semaphore`. Use FastAPI `BackgroundTasks` only for trivial local dev.
3. JD embedding cache: Persist JD embeddings in Mongo `jd_embeddings` keyed by `sha256(job_text + model_version)` with TTL or manual eviction, plus a small in-process LRU for hot entries.

### Data Model Details
- Core candidate fields (simplified): `_id`, `full_name`, `summary`, `skills[]`, `experience_years`, `education[]`, `location`, `created_at`, `updated_at`.
- Embedding metadata: `embedding_vector`, `embedding_model`, `embedding_dimensions`, `embedding_last_generated_at`, `embedding_version`, `embedding_status`, `embedding_error`.
- Dimension integrity: small=1536, large=3072; enforce during write.
- Concatenation template: configurable; include top N experience bullets, skill list, summary; log truncation.

### Schema & Write Validations (Must)
- Validate `embedding_dimensions` equals configured `EMBEDDING_DIM` on every write; reject mismatches.
- Ensure `embedding_model` matches allowed models or migration versions; set `embedding_version` accordingly.
- Exclude raw vectors from API responses by default; enforce projections that omit `embedding_vector`.

### Backfill Logic (Line-by-Line)
1. Load config (batch size, concurrency, retries).
2. Acquire a run-level lock to prevent duplicate coordinators.
3. Query candidates missing/stale embeddings OR eligible for lock reclamation.
4. Chunk IDs (e.g., 100 per batch).
5. For each batch fetch minimal projection.
6. Build embedding input text per candidate.
7. Concurrent embedding calls (bounded semaphore).
7a. Atomic task claim with stale-lock logic:
	- Claim when `embedding_status == "queued"` OR (`embedding_status == "in_progress"` AND `lock_acquired_at < now - lock_ttl`).
	- Set `embedding_status="in_progress"`, `lock_owner`, `lock_acquired_at=now`; increment `claim_attempts`.
	- If `claim_attempts` exceeds threshold, set `embedding_status="error"` and record `embedding_error`.
8. Validate dimensions; classify errors.
9. Prepare bulk updates (success + error cases).
10. Execute unordered bulk write (upsert=false; partial updates to status/embedding fields only).
11. Rate limit handling (429 → exponential backoff + jitter).
12. Skip ready candidates (idempotent).
13. Log progress metrics.
14. Retry failed subset until attempts exhausted.
15. Persist completion summary.
16. Enqueue follow-up for residual failures.

### Candidate Add/Update Workflow
- Upsert base doc with `embedding_status=pending`.
- Enqueue embedding job via abstraction.
- Job re-fetches candidate → build input → embed → update status/vector or error.
- Return candidate sans raw vector (expose status only).

### Search Endpoint Logic
1. Validate JD text; normalize + truncate.
2. Compute `sha256(job_text + model_version)`; check Mongo `jd_embeddings` (persisted cache).
3. If cache miss, generate JD embedding, store in `jd_embeddings` (TTL or manual eviction) and populate in-process LRU.
4. Construct vector search pipeline (k=top_k capped at 100) with filter.
5. Metadata filters: skills (`$all`), experience (`$gte`), location (exact/regex), tags (`$in`).
6. Lean projection (exclude embedding_vector, include score + basic fields).
7. Execute query; measure latency.
8. Return results + timing + cache indicator.

### Feedback Logging Logic
- Validate candidate & JD hash.
- Persist feedback with unique index (candidate, JD hash, user).
- Optional snapshot of candidate result subset stored separately.

### Error Handling & Resilience
- OpenAI: retries on timeouts, 429 backoff, classify network vs fatal.
- Mongo: reconnect strategy, circuit breaker for search if DB down.
- Partial batch failure thresholds; error status for retry later.
- Unified error envelope (`error_code`, `message`, `correlation_id`).

### Rate-Limiting & Cost Controls (Should)
- Token bucket per API key (per-minute) across workers; backoff/queue when depleted.
- Global cost counter and per-tenant daily/monthly caps; emit alerts when thresholds are exceeded.
- Metrics segmented by tenant and model for cost visibility.

### Performance Strategies
- Proper vector index (cosine) + secondary metadata indexes.
- Pre-filtering inside vector stage reduces candidate pool.
- Lean projections minimize payload.
- JD embedding cache (Mongo + in-memory LRU).
- Warm index touch on startup.
- Async I/O; connection pooling.
 - Exclude `embedding_vector` in projections to shrink payloads.
 - Maintain secondary indexes for common filters: `skills`, `experience_years`, `location`.
 - Optional warm-up: load top JD cache entries at startup.

### Security & Multi-Tenancy
- Secrets via environment for MVP (single service OpenAI key).
- Per-tenant OpenAI keys stored encrypted in Vault/KMS and fetched at embed time.
- If accepting client-provided key via header, do not persist raw key; store only a short-lived reference or nothing.
- Auth middleware stub mapping API key header to tenant.
- Rate limiting per tenant.
- Redact sensitive fields in logs.

### Privacy & Retention (Should)
- JD embeddings in `jd_embeddings` with TTL index (e.g., 7–30 days) or manual eviction.
- Search logs retain only non-PII metadata; scrub PII from logs.
- Do not return raw embeddings to clients; projections exclude vectors by default.

### Observability
- JSON structured logs with correlation IDs.
- Prometheus metrics: counters (embedding_requests), histograms (search_latency), gauges (pending_embeddings).
- Health endpoints: liveness & readiness (Mongo + optional OpenAI ping).

### Testing Strategy
- Unit: embedding retries, candidate status transitions, search filter assembly.
- Integration: vector index correctness, ordering of results.
- Load: Locust tasks simulating search concurrency; measure p95 latency.
- Mocks: stub OpenAI responses; deterministic vectors for assertions.

### Extensibility
- Multi-vector (skills vs experience) fields and indexes.
- Personalization: user preference vectors.
- Hybrid search (semantic + keywords) later.
- Migration: dual embedding fields during model switch, active model flag, progressive backfill.

### Background Task Backend Decision
- Production: Async in-process worker (no Celery/Redis) with:
	- Atomic claim using `find_one_and_update`.
	- Fields: `lock_owner`, `lock_acquired_at`, `claim_attempts`, `embedding_status`.
	- Stale-lock TTL (default 10 minutes) for crash recovery.
	- Bounded concurrency via `asyncio.Semaphore` (default 8).
- Local dev only: FastAPI `BackgroundTasks`.
- Rationale: FastAPI-only while ensuring durability for moderate scale.

### Worker Claim & Reclamation (Must)
- Claim filter (pseudo):
	- `embedding_status == "queued"` OR (`embedding_status == "in_progress"` AND `lock_acquired_at < now - lock_ttl`)
	- `claim_attempts < max_claim_attempts`
- Atomic update on claim:
	- Set `embedding_status="in_progress"`, `lock_owner=<worker_id>`, `lock_acquired_at=now`, `updated_at=now`.
	- Increment `claim_attempts` by 1.
- Requeue rules:
	- On retryable failures: set `embedding_status="queued"` with backoff timestamp.
	- On max attempts: set `embedding_status="error"` and record `embedding_error`.

### Configuration Management
- Pydantic Settings; fail-fast if missing critical vars.
- Clear grouping and naming (`OPENAI__API_KEY`, etc.).

### Startup Validations (Must)
- Validate `EMBEDDING_MODEL` ↔ `EMBEDDING_DIM` mapping (e.g., large=3072).
- Validate Mongo vector index exists on `embedding_vector` with matching dimension and cosine metric; fail-fast if missing/mismatched.
- Validate rate-limit and cost-threshold configs; refuse startup if unset.

### Logging & Metrics Nuances
- Batch-level logging not per-candidate to reduce noise.
- Error classification tags; controlled metric label cardinality.

### Idempotency & Consistency
- Skip re-embedding if model/version unchanged and status ready.
- JD cache keyed on hash + model version.

### Operational Scripts
- Create vector index (validate dimension).
- Run backfill with parameters (batch size, concurrency, model).
- Requeue stale/error embeddings.

### Operational Runbook (Should)
- Requeue stuck docs: set `embedding_status="queued"` where `in_progress` and `lock_acquired_at < now - lock_ttl` or after resolving `embedding_error`.
- Safe backfill: batch=100, concurrency=8; monitor rate limits/costs; resume idempotently.
- Rollback bad embeddings: mark affected docs `queued` targeting new `embedding_version`; optionally archive previous vectors.

### Risks & Mitigations
- Dimension mismatch → early validation + halt batch.
- Cost spikes → rate limit + concurrency caps.
- Large documents → projection trimming, optional compression.
 - Lock thrashing on reclamation → cap `claim_attempts`, add backoff windows, alert on repeated reclaim cycles.

### Deployment Considerations
- Readiness probes ensure DB connectivity.
- Memory-safe streaming batches.
- Metrics-driven tuning loop for search latency.

### Immediate Next Decisions
1. Final embedding model (confirm large=3072 for MVP).
2. Initial queue implementation choice (async worker as specified).
3. Cache persistence strategy (Mongo `jd_embeddings` + small LRU).

### Defaults (MVP)
- Embedding model: `text-embedding-3-large` (dimensions=3072).
- Backfill batch size: 100.
- Parallel embedding concurrency: 8.
- Worker lock TTL: 10 minutes.
- Retry policy: max 3; exponential backoff with jitter (base 2s).
- JD cache: Mongo `jd_embeddings` + small in-process LRU.
- Rate limit guard: `max_requests_per_minute` per API key; apply token bucket.

(End of plan – ready for refinement.)