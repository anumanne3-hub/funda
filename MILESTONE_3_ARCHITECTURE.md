# Milestone 3: Document RAG architecture

Status: implementation started. The RAG contracts and source-aware character chunker
exist locally; the end-to-end RAG pipeline and the components below remain planned.

## Resume here

- The agreed worker runs as a GitHub Actions workflow, triggered by the backend for
  manual syncs and chat uploads; scheduled sync is a later addition. Supabase stores
  durable jobs, private files, chunks and vectors. NVIDIA trial endpoints are for
  development/evaluation; production model access requires appropriate terms.
- Existing code: `backend/app/rag/contracts.py` defines scope, source locations,
  evidence and provider interfaces; `backend/app/rag/chunking.py` contains the first
  provenance-preserving chunker. `backend/tests/test_rag_chunking.py` tests it.
- Next: implement migrations and ownership-scoped document/job APIs, then worker claims,
  GitHub dispatch, storage and extractors. Do not expose RAG as available until retrieval,
  citations, authorization and failure paths work end to end.
- On 2026-11-04 the frontend production build passed; backend tests reported 41 passed,
  3 PostgreSQL-only tests skipped; Ruff and mypy passed. Hosted acceptance, final CI,
  and the outstanding Milestone 2 release gates remain unverified.
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
- A schedule can be added after manual sync works. Scheduled reconciliation must recover
  queued jobs after a failed dispatch or abandoned run. No promise of immediate processing
  is made with GitHub-hosted runners.
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
