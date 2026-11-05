import { useEffect, useRef, useState } from "react";
import type { ChangeEvent, FormEvent } from "react";
import {
  createProjectSource,
  deleteRagDocument,
  getIngestionJob,
  listConversationIngestionJobs,
  listConversationUploads,
  listProjectIngestionJobs,
  listProjectSources,
  syncRagDocument,
  uploadConversationFile,
} from "./api/client";
import type { IngestionJob, RagDocument } from "./api/client";

export function RagSources({
  projectId,
  conversationId,
}: {
  projectId: string | null;
  conversationId: string;
}) {
  const [sources, setSources] = useState<RagDocument[]>([]);
  const [uploads, setUploads] = useState<RagDocument[]>([]);
  const [jobs, setJobs] = useState<Record<string, IngestionJob>>({});
  const [url, setUrl] = useState("");
  const [title, setTitle] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const dialogRef = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    let active = true;
    setSources([]);
    setUploads([]);
    setJobs({});
    void Promise.all([
      projectId ? listProjectSources(projectId) : Promise.resolve([]),
      listConversationUploads(conversationId),
      projectId ? listProjectIngestionJobs(projectId) : Promise.resolve([]),
      listConversationIngestionJobs(conversationId),
    ])
      .then(([sourceRows, uploadRows, projectJobs, conversationJobs]) => {
        if (!active) return;
        setSources(sourceRows);
        setUploads(uploadRows);
        const latest: Record<string, IngestionJob> = {};
        for (const job of [...projectJobs, ...conversationJobs]) {
          if (!latest[job.document_id]) latest[job.document_id] = job;
        }
        setJobs(latest);
      })
      .catch((failure: unknown) => {
        if (active) setError(String(failure));
      });
    return () => {
      active = false;
    };
  }, [projectId, conversationId]);

  useEffect(() => {
    const pending = Object.values(jobs).filter(
      (job) => job.status === "queued" || job.status === "running",
    );
    if (!pending.length) return;
    const timer = window.setInterval(() => {
      void Promise.all(
        pending.map(async (job) => {
          try {
            const updated = await getIngestionJob(job.id);
            setJobs((current) => ({
              ...current,
              [updated.document_id]: updated,
            }));
          } catch {
            // Keep the last visible state; the next user action can retry the read.
          }
        }),
      );
    }, 5000);
    return () => window.clearInterval(timer);
  }, [jobs]);

  async function addSource(event: FormEvent) {
    event.preventDefault();
    if (!projectId) return;
    const sourceUrl = url.trim();
    if (sources.some((source) => source.source_key === sourceUrl)) {
      setError("This website is already listed below. Use its Sync button.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const source = await createProjectSource(
        projectId,
        sourceUrl,
        title.trim(),
      );
      setSources((current) => [source, ...current]);
      setUrl("");
      setTitle("");
    } catch (failure) {
      if (String(failure).includes("Source already exists in this project")) {
        void listProjectSources(projectId)
          .then(setSources)
          .catch(() => undefined);
        setError("This website is already listed below. Use its Sync button.");
      } else {
        setError(String(failure));
      }
    } finally {
      setBusy(false);
    }
  }

  async function sync(source: RagDocument) {
    setBusy(true);
    setError(null);
    const keyName = `rag-sync:${source.id}`;
    const key = sessionStorage.getItem(keyName) ?? crypto.randomUUID();
    sessionStorage.setItem(keyName, key);
    try {
      const job = await syncRagDocument(source.id, key);
      setJobs((current) => ({ ...current, [source.id]: job }));
      sessionStorage.removeItem(keyName);
    } catch (failure) {
      setError(String(failure));
    } finally {
      setBusy(false);
    }
  }

  async function remove(source: RagDocument) {
    if (!window.confirm(`Remove ${source.title}?`)) return;
    setBusy(true);
    setError(null);
    try {
      await deleteRagDocument(source.id);
      setSources((current) => current.filter((item) => item.id !== source.id));
      setUploads((current) => current.filter((item) => item.id !== source.id));
    } catch (failure) {
      setError(String(failure));
    } finally {
      setBusy(false);
    }
  }

  async function upload(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setBusy(true);
    setError(null);
    const keyName = `rag-upload:${conversationId}:${file.name}:${file.size}:${file.lastModified}`;
    const key = sessionStorage.getItem(keyName) ?? crypto.randomUUID();
    sessionStorage.setItem(keyName, key);
    try {
      const job = await uploadConversationFile(conversationId, file, key);
      setJobs((current) => ({ ...current, [job.document_id]: job }));
      setUploads((current) => [
        {
          id: job.document_id,
          project_id: null,
          conversation_id: conversationId,
          source_kind: "upload",
          source_key: job.document_id,
          title: file.name,
          created_at: job.created_at,
        },
        ...current,
      ]);
      sessionStorage.removeItem(keyName);
    } catch (failure) {
      setError(String(failure));
    } finally {
      setBusy(false);
    }
  }

  const visibleIds = new Set(
    [...sources, ...uploads].map((source) => source.id),
  );
  const counts = { queued: 0, running: 0, failed: 0, completed: 0 };
  for (const job of Object.values(jobs)) {
    if (visibleIds.has(job.document_id) && job.status in counts) {
      counts[job.status as keyof typeof counts] += 1;
    }
  }
  const statusSummary = (["running", "queued", "failed", "completed"] as const)
    .filter((status) => counts[status] > 0)
    .map((status) => `${counts[status]} ${status}`)
    .join(" · ");

  return (
    <section className="rag-sources" aria-label="Documents and sources">
      <button
        type="button"
        className="rag-sources-open"
        onClick={() => dialogRef.current?.showModal()}
      >
        Documents and sources
        <span className="rag-sources-status" role="status">
          {statusSummary || "No syncs yet"}
        </span>
      </button>
      <dialog
        ref={dialogRef}
        className="rag-sources-dialog"
        aria-labelledby="rag-sources-title"
      >
        <div className="rag-sources-dialog-header">
          <h2 id="rag-sources-title">Documents and sources</h2>
          <button type="button" onClick={() => dialogRef.current?.close()}>
            Close
          </button>
        </div>
        {error && <p role="alert">{error}</p>}
        <label className="rag-upload">
          Upload to this chat (.txt, .md, .html)
          <input
            type="file"
            accept=".txt,.md,.markdown,.html,text/plain,text/markdown,text/html"
            disabled={busy}
            onChange={(event) => void upload(event)}
          />
        </label>
        {uploads.length > 0 && (
          <ul>
            {uploads.map((upload) => (
              <li key={upload.id}>
                <span>{upload.title}</span>
                <span>
                  {" "}
                  · {jobs[upload.id]?.status ?? "Status unavailable"}
                </span>
                {jobs[upload.id]?.error_code && (
                  <span> · {jobs[upload.id].error_code}</span>
                )}
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => void remove(upload)}
                >
                  Remove
                </button>
              </li>
            ))}
          </ul>
        )}
        {projectId && (
          <>
            <h3>Project websites</h3>
            <form onSubmit={(event) => void addSource(event)}>
              <input
                type="url"
                placeholder="Allowed HTTPS URL"
                aria-label="Source URL"
                value={url}
                onChange={(event) => setUrl(event.target.value)}
                required
              />
              <input
                type="text"
                placeholder="Source title"
                aria-label="Source title"
                value={title}
                onChange={(event) => setTitle(event.target.value)}
                required
              />
              <button type="submit" disabled={busy}>
                Add source
              </button>
            </form>
            <p>Only website URLs enabled for this app can be added.</p>
            {sources.length === 0 && (
              <p>No websites added to this project yet.</p>
            )}
            <ul>
              {sources.map((source) => (
                <li key={source.id}>
                  <span>{source.title}</span>
                  <small>{source.source_key}</small>
                  <span>{jobs[source.id]?.status ?? "Not synced"}</span>
                  {jobs[source.id]?.error_code && (
                    <span> · {jobs[source.id].error_code}</span>
                  )}
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => void sync(source)}
                  >
                    Sync
                  </button>
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => void remove(source)}
                  >
                    Remove
                  </button>
                </li>
              ))}
            </ul>
          </>
        )}
      </dialog>
    </section>
  );
}
