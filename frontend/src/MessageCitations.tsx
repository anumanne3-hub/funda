import { useEffect, useState } from "react";
import { listMessageCitations } from "./api/client";
import type { MessageCitation } from "./api/client";

function location(citation: MessageCitation): string {
  const parts = [
    citation.page === null ? null : `Page ${citation.page}`,
    citation.section,
    citation.start_ms === null
      ? null
      : `${Math.floor(citation.start_ms / 1000)}s${citation.end_ms === null ? "" : `–${Math.floor(citation.end_ms / 1000)}s`}`,
  ];
  return parts.filter(Boolean).join(" · ");
}

export function MessageCitations({
  messageId,
  content,
}: {
  messageId: string;
  content: string;
}) {
  const [citations, setCitations] = useState<MessageCitation[]>([]);
  useEffect(() => {
    let active = true;
    void listMessageCitations(messageId)
      .then((rows) => {
        if (active) setCitations(rows);
      })
      .catch(() => {
        if (active) setCitations([]);
      });
    return () => {
      active = false;
    };
  }, [messageId, content]);
  if (!citations.length) return null;
  return (
    <section className="message-citations" aria-label="Sources">
      <strong>Sources</strong>
      <ol>
        {citations.map((citation) => {
          const detail = location(citation);
          const url = citation.source_url;
          const safeUrl = url && /^https:\/\//i.test(url) ? url : null;
          return (
            <li key={`${citation.ordinal}-${citation.chunk_id}`}>
              <span>[{citation.ordinal}] </span>
              {safeUrl ? (
                <a href={safeUrl} target="_blank" rel="noopener noreferrer">
                  {citation.title}
                </a>
              ) : (
                <span>{citation.title}</span>
              )}
              {detail && <span className="citation-location"> · {detail}</span>}
            </li>
          );
        })}
      </ol>
    </section>
  );
}
