CREATE SCHEMA IF NOT EXISTS extensions;
CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA extensions;

-- The chosen NVIDIA development model emits 2048 dimensions. Retrieval will
-- read only ready versions with the matching model and dimension.
ALTER TABLE document_chunks ADD COLUMN embedding extensions.vector(2048);
