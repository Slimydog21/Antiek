import { useCallback, useState } from "react";
import {
  fetchTwinNotes,
  recordTwinNote,
  type TwinNotesResponse,
} from "../../api/engagement";
import { SandboxedHtmlFrame } from "../windows/HostedHtmlDocumentHost";

export type TwinNotesPanelProps = {
  assetId: string;
  spawnId?: string | null;
};

export function TwinNotesPanel({
  assetId,
  spawnId = null,
}: TwinNotesPanelProps) {
  const [twins, setTwins] = useState<TwinNotesResponse | null>(null);
  const [text, setText] = useState("");
  const [kind, setKind] = useState<"insight" | "question">("insight");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const t = await fetchTwinNotes(assetId, { includeHtml: true });
      if (t.view_format !== "html") {
        throw new Error("twin notes view_format must be html");
      }
      setTwins(t);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, [assetId]);

  const record = useCallback(async () => {
    if (!text.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const t = await recordTwinNote({
        asset_id: assetId,
        kind,
        text: text.trim(),
        source_spawn_id: spawnId,
        include_html: true,
      });
      if (t.view_format !== "html") {
        throw new Error("twin notes view_format must be html");
      }
      setTwins(t);
      setText("");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, [assetId, kind, text, spawnId]);

  return (
    <section
      className="twin-notes-panel"
      data-testid="twin-notes-panel"
      data-view-format="html"
      aria-label="Twin notes"
    >
      <header>
        <h2>Twin notes</h2>
        <p className="meta">
          Recursive note-taker for asset <code>{assetId}</code>
        </p>
      </header>
      <div className="controls" style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
        <select
          data-testid="twin-kind"
          value={kind}
          onChange={(e) => setKind(e.target.value as "insight" | "question")}
          disabled={busy}
        >
          <option value="insight">insight</option>
          <option value="question">question</option>
        </select>
        <input
          type="text"
          data-testid="twin-text"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Insight or question…"
          disabled={busy}
          style={{ minWidth: "12rem", flex: 1 }}
        />
        <button
          type="button"
          data-testid="twin-record"
          onClick={() => void record()}
          disabled={busy || !text.trim()}
        >
          Record
        </button>
        <button
          type="button"
          data-testid="twin-refresh"
          onClick={() => void load()}
          disabled={busy}
        >
          Refresh
        </button>
      </div>
      {error ? (
        <p className="error" role="alert">
          {error}
        </p>
      ) : null}
      {twins ? (
        <div data-testid="twin-notes-summary" className="font-mono text-sm">
          <p>
            notes={twins.note_count} · insights={twins.insight_count} · questions=
            {twins.question_count}
          </p>
          <ul data-testid="twin-notes-list">
            {twins.notes.map((n) => (
              <li key={n.note_id}>
                <strong>[{n.kind}]</strong> {n.text}
              </li>
            ))}
          </ul>
          {twins.html ? (
            <div className="flex h-40" data-testid="twin-notes-html">
              <SandboxedHtmlFrame html={twins.html} title="Twin notes preview" />
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

export default TwinNotesPanel;
