# Milestone 3 RAG deployment and acceptance

RAG chat is gated by `RAG_CHAT_ENABLED=false`. Keep it disabled until the checks below pass
on a disposable hosted project and again on the intended deployment. Text, Markdown, HTML,
and allowlisted single-page websites are the implemented source types. PDF, image, audio,
and cloud-folder ingestion are not yet available.

## Deploy in order

1. Apply every `supabase/migrations/2026110400*.sql` migration. Confirm the `vector`
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
5. Keep `RAG_CHAT_ENABLED=false` while running ingestion and retrieval acceptance.
   Set `RAG_EMBEDDING_API_KEY` on Render only when ready to test chat retrieval.
   The embedding model and dimensions must match between Render and Actions.

The `rag-ingest.yml` workflow handles individual dispatches and reconciles up to 20 queued
or expired jobs every 30 minutes. Its scheduled cleanup handles at most 20 soft-deleted
documents and 100 queued object deletions per run. GitHub schedules are not a latency
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
2. Upload a small UTF-8 `.txt`, `.md`, and `.html` file into a conversation. Confirm each
   has a completed job and appears after reload. Reject an unsupported file and an
   oversized file without creating a document or job.
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

Enable `RAG_CHAT_ENABLED=true` only after hosted acceptance, provider access and quotas,
and the outstanding Milestone 2 release gates are verified. If ingestion or retrieval
fails after enablement, set `RAG_CHAT_ENABLED=false` and redeploy the API. This disables
grounded chat without deleting indexed data or queued cleanup work. Investigate failed
jobs by their sanitized `error_code`; retry only through a new sync request or the
scheduled recovery flow. Do not manually mark a failed version ready.
