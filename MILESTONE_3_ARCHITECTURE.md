# Milestone 3: Document RAG architecture

Status: implementation started. RAG contracts, source-aware chunking, and the first
document/job metadata migration exist locally. The end-to-end RAG pipeline remains planned.

## Resume here

Pause point (2026-11-04): Next, add bounded PDF extraction when a parser dependency is
available, then image/audio extraction or provider adapters. Run the disposable PostgreSQL
suite with pgvector, followed by the hosted checks in `docs/rag-operations.md`. Keep
`RAG_CHAT_ENABLED=false` until those checks pass. Current local verification: 78 backend
tests passed, 4 PostgreSQL-only tests skipped; Ruff, mypy, and frontend build/lint/format
checks passed. All Milestone 3 changes are still uncommitted in this working tree.

- The agreed worker runs as a GitHub Actions workflow, triggered by the backend for
  manual syncs and chat uploads. A scheduled reconciliation run now scans up to 20 queued
  or lease-expired jobs every 30 minutes. Supabase stores
  durable jobs, private files, chunks and vectors. NVIDIA trial endpoints are for
  development/evaluation; production model access requires appropriate terms.
- Existing code: `backend/app/rag/contracts.py` defines scope, source locations,
  evidence and provider interfaces; `backend/app/rag/chunking.py` contains the first
  provenance-preserving chunker. `backend/tests/test_rag_chunking.py` tests it.
- Project website sources can now be registered only when their exact URL is configured in
  `RAG_ALLOWED_SOURCE_URLS`. Owner-scoped document/job reads, soft deletion and idempotent
  sync enqueue are implemented. Transactional worker claims, bounded leases, renewals,
  retries and stale-worker rejection are implemented. A bounded website fetch adapter now
  validates allowlisted HTTPS URLs and resolved public addresses on each redirect and pins
  the connection to the validated address. Bounded UTF-8 text, Markdown and HTML extraction
  is implemented with HTML section provenance. The API can dispatch a committed job to a
  configured GitHub workflow; failure leaves it queued, and replay can retry dispatch.
  A one-job worker orchestrator now claims a requested job, bounds processing time and
  persists completion or sanitized errors. A private Supabase Storage adapter now supports
  bounded original upload, authenticated download and deletion with version-specific keys.
  Signed-in users can upload bounded text, Markdown and HTML files to their own conversation;
  the API stores the original privately and creates an idempotent queued job. Website
  preparation now combines bounded fetch, extraction, hashing and provenance-preserving
  chunking, but does not publish an indexed version. The development embedding adapter uses
  NVIDIA `nemotron-3.5-embed-1b` with validated 2048-dimensional output; a pgvector migration
  and pgvector-enabled CI database are added. The text ingestion processor handles website
  sources and conversation uploads, writes vectors and publishes a version in one database
  transaction. A GitHub Actions workflow runs the worker for a dispatched job. Hosted
  storage, provider access, PostgreSQL migration and workflow execution remain unverified.
  Scoped vector retrieval now checks ownership, project/conversation association, deletion,
  readiness and embedding model in the database query. The PostgreSQL retrieval test is
  pending a pgvector-enabled test database. A feature-gated chat path builds grounded
  prompts, handles insufficient evidence, and persists version-specific citations with an
  owner-scoped read endpoint. The chat UI now loads and displays citation snapshots for
  completed assistant messages, including after a reload. `RAG_CHAT_ENABLED` remains false
  by default.
- The frontend now lets signed-in users register allowed project websites, request syncs,
  upload text/Markdown/HTML into the active chat, and watch job status. Owner-scoped
  conversation upload and project/conversation job list endpoints restore documents and
  their latest job states after reload. Each list is bounded to 100 records; pagination
  is still needed for larger histories. The production build, lint and formatting checks
  passed. Fixed citation cases and a PostgreSQL ranking fixture bring backend verification
  to 78 passed tests
  (4 PostgreSQL-only skips); Ruff and mypy pass.
- Scheduled cleanup now removes derived rows for explicitly deleted documents after a
  one-hour grace period. Private object keys are queued transactionally before document,
  conversation, project or account rows are deleted, so cascading database deletes preserve
  the work needed to remove originals. Storage deletion is retryable and treats an already
  missing object as complete. The new storage-deletion migration needs hosted verification.
- Citation numbers now start at 1 in saved snapshots, matching answer markers. Fixed
  cases reject missing, out-of-range and mixed invalid markers. The PostgreSQL fixture
  asserts ranking order but remains skipped until a pgvector test database is available.
  Only passages actually cited by an answer are saved, retaining their original marker
  numbers (for example, a sole `[2]` citation remains source 2 in the UI).
  These deterministic cases check citation syntax and ordering; they do not measure model
  factual support on a hosted provider.
- `docs/rag-operations.md` now records deployment inputs, migration and bucket order,
  local/CI checks, hosted authorization and failure acceptance, and a feature-flag rollback.
  None of those hosted checks has been performed yet.
- Next: add PDF/image/audio extractors, hosted retrieval quality evaluations and hosted
  acceptance. PDF extraction needs a parser dependency; the package
  registry was unreachable in this workspace. Do not expose RAG as available until
  authorization and failure paths work end to end on the hosted stack.
- On 2026-11-04 backend tests reported 78 passed, 4 PostgreSQL-only tests skipped;
  Ruff and mypy passed. The citation UI production build, lint and formatting checks passed
  using the repository's bundled Node runtime. Hosted acceptance, final
  CI, and the outstanding Milestone 2 release gates remain unverified.
- These changes and earlier UI/Help changes are uncommitted in the working tree. Preserve
  them when resuming; the architecture document is itself not yet tracked by Git.

## Purpose

Allow a signed-in user to index project sources and conversation uploads, ask questions,
and inspect citations. A later orchestrator can call the retrieval service through an
explicit interface; it does not need to manage storage, ingestion, or embeddings.

## Components and responsibilities

1. **Web UI (Vercel):** select a project, configure permitted sources, upload to a chat,
   request a sync, show job status, and display citations. The browser has no privileged
   GitHub, storage, database, or model credentials.
2. **API (Render):** authenticate and authorize every request; validate upload and source
   configuration; create durable ingestion jobs; request a worker run; serve status and
   citations; and invoke retrieval during chat. A failed workflow dispatch leaves a
   visible queued job for a later dispatch; it is not reported as indexed.
3. **Ingestion job store (Supabase PostgreSQL):** persist owners, scope, status, attempts,
   bounded leases, errors, timestamps, and idempotency keys. Workers claim jobs atomically;
   expired leases may be reclaimed. Every externally visible state transition is durable.
4. **Worker (GitHub Actions):** a short-lived Python process claims queued jobs and runs
   the same pipeline whether the request came from a chat upload, a manual source sync,
   or a future scheduled workflow. A run is not treated as an always-on worker: startup
   may be delayed, dispatch can fail, and scheduled runs can be delayed or dropped.
5. **Source adapters:** list changes from a configured cloud-accessible folder or bucket,
   or fetch an explicitly configured website. Adapters return source identity, metadata,
   content and completion status. Local laptop folders need a separate local uploader;
   GitHub-hosted runners cannot see them automatically.
6. **Extractors and chunker:** validate and extract PDF, text, Markdown, image, audio and
   HTML content; preserve page, location, and timestamp provenance. OCR/vision and speech
   transcription are separate provider interfaces. Treat all extracted text as untrusted.
7. **Embedding provider:** turn versioned chunks and queries into vectors with the same
   model and dimension. NVIDIA's hosted trial is for evaluation under its applicable
   terms; production needs appropriately licensed provider access. Record model and
   version, limit usage, and never silently mix incompatible vector spaces.
8. **Storage and vector index (Supabase):** originals in a private bucket; documents,
   versions, chunks, provenance and vectors in PostgreSQL with pgvector. Publication of
   a new document version is atomic: retrieval reads only successfully indexed versions.
9. **Retrieval service:** accepts an authenticated owner, project, optional conversation,
   query, and bounded result limit. It applies ownership, project, conversation, readiness
   and deletion filters in the database query before ranking. Returns text and structured
   citations, never raw storage credentials. Anonymous and cross-project access are denied.
10. **Answer service:** passes retrieved evidence as untrusted data to the model, requests
    grounded answers, returns citations, and reports insufficient or unavailable evidence.
    Persist citations with the assistant response so they survive reload and identify the
    exact document version and source location.
11. **Future orchestrator (Milestone 6):** selects among approved retrieval/context services,
    validates a bounded plan, and checks support for answers. Milestone 3 exposes the
    retrieval boundary; it does not claim to implement intent classification or planning.

```text
Project sources ─┐
Chat upload ─────┼─> API: authorize + enqueue ─> Supabase job store
Manual sync ─────┘                                  │
                                                    ▼
                                    GitHub Actions worker
                           fetch → validate → extract → chunk → embed
                                                    │
                                      private storage + pgvector

Chat question → API / future orchestrator → scoped retrieval → grounded answer + citations
```

## Scope and operational rules

- Project sources are available only to their owning user within that project. Chat
  uploads are limited to their owning conversation unless explicitly promoted later.
- Syncs use stable source IDs and content hashes. An unchanged source is not re-embedded;
  failed or incomplete listings never imply deletion. Explicitly deleted sources must be
  excluded from search immediately, with retryable cleanup of storage and derived data.
- Uploads require bounded size, type detection, PDF page/encryption checks, and extraction
  limits. Web fetching requires an allowlist, public-address validation on every redirect,
  timeouts, response limits, and an explicit crawl scope to prevent access to internal URLs.
- GitHub dispatch happens server-side with a narrowly scoped credential. The worker reads
  only required secrets, does not print source content or credentials, and operates with
  bounded batches, timeouts, retry limits and failure reporting. Workflow concurrency is
  an optimization; database claims and idempotency are the source of correctness.
- Scheduled reconciliation recovers queued jobs after a failed dispatch or abandoned run.
  Hosted schedule execution is unverified. No promise of immediate processing is made with
  GitHub-hosted runners.
- CI uses local fakes for storage, embeddings and extraction; production secrets and trial
  endpoints are not required for tests. Changing an embedding model requires re-indexing.

## Implementation and acceptance order

1. Define database migrations, private storage, document and job contracts, and scoped
   authorization tests. Confirm the pgvector extension and selected embedding dimensions.
2. Implement upload/source APIs and durable jobs, then the worker's atomic claims, leases,
   retry and GitHub Actions dispatch. Test interruptions, duplicate delivery, and cleanup.
3. Add source adapters and bounded extractors for text, PDF, images and audio. Configure
   and verify NVIDIA trial endpoints for development only; use mocks in automated tests.
4. Implement scoped vector retrieval, evidence-bearing prompt construction, persisted
   citations and the chat/project UI. Verify insufficient evidence and access isolation.
5. Add fixed retrieval/citation evaluations, operational documentation and a deployment
   checklist. Run local and PostgreSQL tests, CI, migrations, and hosted acceptance before
   marking the milestone complete. Resolve the outstanding Milestone 2 release gates.

## Deployment inputs needed

- A private Supabase Storage bucket and migration access, including pgvector support.
- A GitHub credential able to dispatch only the intended repository workflow, and worker
  secrets provisioned outside the repository. Confirm workflow access and free-tier limits.
- A cloud-accessible source folder or bucket and a fixed set of allowed website URLs.
- Evaluation credentials and chosen models/dimensions for embeddings, image understanding,
  and transcription; production-approved providers and their quotas before public use.
- An explicit retention policy for source files and chat uploads, plus a schedule when ready.
