# Milestone 3.1: Additional RAG sources

## Status (2026-11-16)

Work has started. Milestone 3 remains functionally implemented with its hosted
release gate open; this tracker preserves that distinction. Baseline backend
tests: 93 passed, 4 PostgreSQL-only skipped. After the image OCR slice,
98 passed and 4 skipped in the full suite; the subsequent image upload-to-worker
test passed in an 11-test focused run. Ruff and mypy passed. Frontend build passed after the
RAG Help update. Hosted PDF upload and RAG answers were confirmed by the user;
the full hosted acceptance matrix is still open in `docs/rag-operations.md`.

## Implementation order

1. **Image:** bounded upload validation, private original, OCR/vision extraction,
   page or image location, chunking, embedding, scoped retrieval, citation display,
   cleanup, fixed evaluation cases, then hosted acceptance. PNG/JPEG header,
   size, and pixel-count validation is implemented. A disabled backend flag
   (`RAG_IMAGE_UPLOAD_ENABLED`, default `false`) gates image uploads. The
   Render blueprint now sets it to `true`; this change is not deployed until
   the repository is committed and deployment checks pass. The browser queries
   the API capability and offers PNG/JPEG selection only when enabled. The
   worker uses local English Tesseract OCR and indexes text under an `Image`
   section citation. Both the worker and CI install Tesseract. A real PNG OCR
   test runs in CI and skips on development machines without Tesseract. The
   local upload-to-worker test covers the flag, malformed signature, job
   completion, and image metadata using a fake OCR response. Full image
   decoding, real CI OCR result, citation display, and hosted acceptance are
   still unverified.
2. **Audio:** size and duration validation, private original, bounded
   transcription with timestamps, timestamped chunks and citations, cleanup,
   fixed evaluations, then hosted acceptance.
3. **Cloud folder or bucket:** owner authorization, stable identities,
   incremental listing, incomplete-scan safety, removal handling, then hosted
   acceptance. A local device folder needs a separate uploader.

Each adapter must record extractor/provider versions, enforce its own limits
and cost controls, and reuse the existing job, scope, and deletion rules. No
new source type is enabled until it can complete ingestion and produce a cited
answer in a test environment. Milestone 3.1 remains **in progress**.
