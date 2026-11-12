# Milestone 3 RAG deployment and acceptance

The Render blueprint currently sets `RAG_CHAT_ENABLED=true`. Text, Markdown, HTML,
PDF uploads, and allowlisted single-page websites are implemented; image, audio,
and cloud-folder ingestion are not yet available. A NASA Earth website sync and cited
answer have worked on the hosted app, but the full acceptance checklist below
has not been recorded. An earlier conversation upload returned HTTP 503 and
still requires a successful hosted retest. Treat this as an open release gate.

## Deploy in order

1. Apply every RAG migration in `supabase/migrations/` dated 2026-11-04 or later,
   including the project-source uniqueness update. Confirm the `vector`
   extension, the 2048-dimensional `document_chunks.embedding` column, and the
   `storage_deletions` table. Do not reset an existing database.
2. Create a private Supabase Storage bucket matching `RAG_STORAGE_BUCKET` (default
   `rag-private`). The bucket must not allow public object reads.
3. Set these Render backend variables privately: `RAG_STORAGE_URL`,
   `RAG_STORAGE_SERVICE_KEY`, `RAG_STORAGE_BUCKET`, `RAG_ALLOWED_SOURCE_URLS`,
   `RAG_DISPATCH_REPOSITORY`, `RAG_DISPATCH_REF`, and `RAG_DISPATCH_TOKEN`.
   Use a Supabase secret API key (`sb_secret_...`) from Project Settings > API Keys
   for `RAG_STORAGE_SERVICE_KEY`; never use a publishable key or expose it to the browser.
   `RAG_ALLOWED_SOURCE_URLS` is a comma-separated list of exact HTTPS page URLs.
4. Set GitHub Actions secret values `RAG_DATABASE_URL`, `RAG_STORAGE_URL`,
   `RAG_STORAGE_SERVICE_KEY`, and `RAG_EMBEDDING_API_KEY`. Set Actions variables
   `RAG_STORAGE_BUCKET` and `RAG_ALLOWED_SOURCE_URLS`. The database URL must use
   the hosted PostgreSQL database with the access needed for worker writes. Grant the
   dispatch token access only to the intended repository workflow.
5. Confirm `RAG_EMBEDDING_API_KEY` is configured on Render before chat retrieval
   acceptance. The embedding model and dimensions must match between Render and
   Actions. If hosted RAG fails, set `RAG_CHAT_ENABLED=false` and redeploy.

The `rag-ingest.yml` workflow handles individual dispatches and reconciles up to 20 queued
or expired jobs at 00:00, 05:00, 10:00, 15:00 and 20:00 UTC. Its scheduled cleanup handles
at most 20 soft-deleted documents and 100 queued object deletions per run. GitHub schedules are not a latency
guarantee. An object deletion failure leaves its key in `storage_deletions` for retry.

## Local and CI verification

From `backend`, run `ruff format --check app tests`, `ruff check app tests`, `mypy app`,
and `pytest -q` through the project's environment. The PostgreSQL tests require a
disposable `funda_test_*` database with pgvector; set `TEST_DATABASE_URL` only to that
database. Confirm the migration, retrieval, worker-claim, and concurrency tests run
rather than skip. Run the frontend build, lint, and formatting checks using the bundled
Node installation described in the README.

## Hosted acceptance

Use two new test accounts and a project owned by the first account.

1. Register one URL from `RAG_ALLOWED_SOURCE_URLS` and one URL outside it. Confirm the
   first registers and the second is rejected. Sync the allowed source; watch the job
   move from queued through running to completed. Reload and confirm its status remains.
2. Upload a small UTF-8 `.txt`, `.md`, `.html`, and a text PDF into a conversation. Confirm each
   has a completed job and appears after reload. Reject an unsupported file and an
   oversized file without creating a document or job. Reject an encrypted PDF;
   confirm the text PDF cites the right page.
   Create a second conversation in the same project: it should show the synced
   project website but not the first chat's uploaded file. Confirm a new chat
   created from a project chat inherits that project.
3. With RAG chat enabled on a test deployment, ask a question answered by a known source.
   Confirm the answer cites `[1]` or another shown source number, the Sources panel
   points to the correct document/version/location, and citations remain after reload.
   Ask a question with no indexed evidence and confirm the insufficient-evidence answer.
4. Confirm the second account gets no access to the first account's project sources,
   uploads, jobs, or message citations. Confirm a chat in another project cannot retrieve
   the first project's chunks. Test a deleted source is excluded from retrieval immediately.
5. Interrupt a worker after it claims a job. Confirm the lease expires and the scheduled
   run either completes a retry or records a terminal failure after the attempt limit.
   Disable workflow dispatch for one request and confirm the job remains visibly queued
   until reconciliation.
6. Delete a source, conversation, project, and account containing private originals.
   Confirm the object keys enter `storage_deletions` and later disappear after cleanup;
   verify the corresponding private objects are gone. Saved citation snapshots should
   remain for messages that still exist.

Record job IDs, timestamps, expected and actual results, and the deployment revision for
each check. Do not record source contents or credentials in logs or issue comments.

## Release decision and rollback

Before declaring the enabled RAG path released, complete hosted acceptance, provider
access and quota checks, and outstanding Milestone 2 release gates. If ingestion or retrieval
fails, set `RAG_CHAT_ENABLED=false` and redeploy the API. This disables
grounded chat without deleting indexed data or queued cleanup work. Investigate failed
jobs by their sanitized `error_code`; retry only through a new sync request or the
scheduled recovery flow. Do not manually mark a failed version ready.
