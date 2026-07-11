import { useEffect, useRef, useState } from "react";

import { appendResearchArtifactNote, researchArtifactViewUrl } from "../../lib/api";
import { useInWindow } from "./windowHostContext";

export interface ResearchArtifactHostProps {
  investigation_id?: string;
  content_hash?: string;
  /** Intentionally ignored: the iframe URL is derived from canonical identity. */
  view_url?: string;
}

/** Window-native, origin-isolated host for the canonical private artifact. */
export default function ResearchArtifactHost({
  investigation_id: investigationId = "",
  content_hash: contentHash = "",
}: ResearchArtifactHostProps) {
  useInWindow();
  const normalizedId = investigationId.trim();
  const normalizedHash = contentHash.trim();
  const frameRef = useRef<HTMLIFrameElement>(null);
  const [status, setStatus] = useState<"" | "saving" | "saved" | "pending" | "error">("");
  const [reloadKey, setReloadKey] = useState(0);
  const savingRef = useRef(false);

  useEffect(() => {
    function receive(event: MessageEvent<unknown>) {
      if (event.source !== frameRef.current?.contentWindow || event.origin !== "null") return;
      const data = event.data;
      if (!data || typeof data !== "object") return;
      const message = data as Record<string, unknown>;
      if (
        message.version !== 1 ||
        message.type !== "antiek.research-artifact.append-note" ||
        message.investigation_id !== normalizedId ||
        typeof message.note !== "string" ||
        !message.note.trim() ||
        message.note.length > 20_000 ||
        typeof message.expected_content_hash !== "string" ||
        !/^[a-f0-9]{64}$/.test(message.expected_content_hash) ||
        savingRef.current
      ) return;

      savingRef.current = true;
      setStatus("saving");
      void appendResearchArtifactNote(
        normalizedId,
        message.note,
        message.expected_content_hash,
      ).then((result) => {
        savingRef.current = false;
        setStatus(result.event_pending ? "pending" : "saved");
        setReloadKey((key) => key + 1);
      }).catch(() => {
        savingRef.current = false;
        setStatus("error");
        // The canonical file may have committed before its audit event failed.
        // Reload so any retry carries the server's current optimistic hash.
        setReloadKey((key) => key + 1);
      });
    }
    window.addEventListener("message", receive);
    return () => window.removeEventListener("message", receive);
  }, [normalizedId]);

  if (!normalizedId || !/^[a-f0-9]{64}$/.test(normalizedHash)) {
    return (
      <p className="p-4 text-sm text-emperor" role="alert">
        Research artifact unavailable: missing investigation identity or content hash.
      </p>
    );
  }

  return (
    <div className="relative h-full min-h-64 w-full">
      <iframe
        key={reloadKey}
        ref={frameRef}
        className="h-full min-h-64 w-full border-0 bg-white"
        data-testid="research-artifact-frame"
        src={researchArtifactViewUrl(normalizedId)}
        sandbox="allow-scripts"
        title={`Research artifact · ${normalizedId}`}
      />
      {status && (
        <p className="absolute bottom-2 right-2 rounded bg-white/90 px-2 py-1 text-xs text-emperor" role="status">
          {status === "saving"
            ? "Saving note…"
            : status === "saved"
              ? "Note saved"
              : status === "pending"
                ? "Note saved · indexing pending"
                : "Note not saved"}
        </p>
      )}
    </div>
  );
}
