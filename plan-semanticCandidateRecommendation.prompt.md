# Plan: Semantic Candidate Recommendation Backend (Azure OpenAI)

FastAPI + MongoDB Atlas backend that embeds *userprofiles* and *jobcollections* with Azure OpenAI (`text-embedding-3-large`, 3072 dims) to power two search routes: (1) applied-only candidates from `ApplicationCollection` filtered by `jobId` + `currentStatus="Applied"`, (2) global database search of all `userprofiles`. Requirements focus on embedding correctness, caching, pagination defaults (applied=50/page by default, global default=50 but HR-configurable), and keeping the backfill + update workflows for both collections. Non-scoped features (feedback, telemetry extras, etc.) are removed for now.

---

## Targets & Constraints
1. **Data sources**
   - `userprofiles`: canonical candidate documents, must store `embedding_vector`, `embedding_vector_size=3072`, `embedding_model`, `embedding_status`, `embedding_updated_at`.
   - `ApplicationCollection`: `candidateId`, `jobId`, `currentStatus`, `appliedAt`, supporting filters for applied-only route.
   - `jobcollections`: job postings; each gets `job_embedding_vector`, `embedding_vector_size=3072`, `job_embedding_model`, `job_embedding_updated_at`.
2. **Azure configuration** (documented in `app/config/settings.py` and `.env`):
   - `AZURE_OPENAI_ENDPOINT=https://chinniai.openai.azure.com/`
   - `AZURE_OPENAI_API_KEY`
   - `AZURE_OPENAI_API_VERSION=2024-02-01`
   - `AZURE_OPENAI_EMBEDDING_DEPLOYMENT=text-embedding-3-large`
3. **Naming clarity**: ensure unique filenames per domain:
   - `app/models/user_profile_models.py`, `app/models/job_listing_models.py`, `app/models/search_models.py`
   - `app/routes/search_candidates_routes.py`
   - `app/services/user_profile_service.py`, `app/services/job_listing_service.py`, `app/services/search_service.py`, `app/services/embedding_service.py`
4. **Backfill coverage**: keep scripts/workflows that regenerate embeddings when missing/stale for both `userprofiles` and `jobcollections`.

---

## Embedding & Backfill Strategy
1. **Candidate lifecycle**
   - On new registration or profile update, enqueue embedding job; persist status and set `embedding_vector_size=3072`.
   - If candidate edits skills/experience/etc., mark embedding stale → regenerate before reusing in search.
2. **Job lifecycle**
   - Generate embeddings for each `jobcollections` document using combined text template:  
     `title | employmentType | workModel | experienceRange summary | skillsRequired list | industry list | locations list | description`.
   - Cache embeddings keyed by `(jobId, updatedAt)`; store vector in job doc, skip dimension/version fields except `embedding_vector_size`.
3. **Backfill scripts**
   - `scripts/backfill_userprofiles_embeddings.py`
   - `scripts/backfill_jobcollections_embeddings.py`
   - Each script scans for docs missing vectors or with `embedding_status != "ready"`, regenerates asynchronously, enforces `embedding_vector_size=3072`.

---

## Search Routes & Logic

### Applied-Candidates Route (`GET /search/applied`)
1. Inputs: `jobId` (required), `count` (default 50, max 100), pagination via `page` or `offset`.
2. Workflow:
   - Fetch job doc; return 404 if missing.
   - Build JD text (title + description + experienceRange + skillsRequired + industry + locations) and fetch cached embedding (regenerate if job updated).
   - Query `ApplicationCollection` for `{ jobId, currentStatus: "Applied" }`, collect `candidateId`s.
   - Pull enriched candidate docs from `userprofiles` (only those with embeddings).
   - Rank using cosine similarity between candidate vectors and JD embedding; optionally apply secondary scorer (e.g., weighted skill overlap) to break ties.
   - Sort descending (best match first), apply pagination (default 50/page), return metadata (`page`, `pageSize`, `totalMatches`, `scores`).

### Global-Candidates Route (`GET /search/global`)
1. Inputs: `jobId` (for JD context), `count` (default 50, HR can request up to 200).
2. Workflow:
   - Reuse JD embedding from cache.
   - Run vector search over entire `userprofiles` collection; optional filters (skills, locations) can be added later.
   - Return top `count` results sorted by similarity, including metadata and source indicator (`"global"`).

---

## Ranking Approach (Best Practice)
- Primary measure: cosine similarity (MongoDB Atlas vector index).
- Optional enhancement: combine cosine score with structured match signals (e.g., exact skill overlaps, experience range alignment) using a weighted linear combination. Keep design open so alternative match algorithms (e.g., Maximal Marginal Relevance, semantic re-rankers) can be plugged in later without API changes.

---

## Implementation Steps (Logic Only)

1. **Models (`app/models/`)**
   - `user_profile_models.py`: `UserProfileInDB`, `UserProfileEmbeddingMeta`, request/response DTOs; ensure projections omit vectors by default.
   - `job_listing_models.py`: `JobListingInDB`, `JobEmbeddingMeta`.
   - `search_models.py`: `AppliedSearchRequest`, `AppliedSearchResponse`, `GlobalSearchRequest`, `SearchCandidateHit`.
2. **Config (`app/config/settings.py`)**
   - Add Azure env vars; enforce `EMBEDDING_VECTOR_SIZE=3072`.
3. **Embedding Service (`app/services/embedding_service.py`)**
   - Wrap Azure OpenAI client; build text templates for candidates/jobs; validate vector length; caching helper for JD embeddings.
4. **User Profile Service**
   - CRUD for `userprofiles`, embedding queue integration, `_mark_embedding_pending` on updates, `_refresh_embedding_status`.
5. **Job Listing Service**
   - Fetch job by `jobId`, manage job embedding fields, hook for backfill script.
6. **Search Service**
   - Methods: `search_applied(jobId, count, pagination)` and `search_global(jobId, count)`.
   - Shared helper to fetch/calc JD embedding, query vector index, join `ApplicationCollection`, apply ranking.
7. **Routes (`app/routes/search_candidates_routes.py`)**
   - Expose `/search/applied` and `/search/global`, validate inputs, call service, format response.
8. **Backfill Scripts**
   - Update existing script(s) to handle `userprofiles` & `jobcollections`, documenting CLI options (batch size, limit, dry run).
9. **Testing**
   - Unit: embedding text builders, service pagination, ranking order assertions.
   - Integration: vector search end-to-end using deterministic vectors.
10. **Operations**
    - Document environment variables, caching strategy, pagination defaults in README if needed.

---

## Additional Notes
- `ApplicationCollection` logic relies on candidate data already being in `userprofiles`; 
- Embedding queues should be async-friendly (e.g., background worker using Mongo locks or queue service). Implementation detail can be decided later but must support automatic re-embedding on profile/job updates.
- Observability, feedback, and telemetry sections intentionally deferred until these core routes stabilize.
- Ensure code is modular to allow future enhancements (e.g., adding filters, alternative ranking strategies) without breaking existing APIs.
- Follow best practices for security, error handling, and performance optimization in FastAPI + MongoDB contexts.