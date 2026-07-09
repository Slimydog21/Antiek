/**
 * TwinNotesPanel — recursive note-taker UI for insights/questions on an asset.
 *
 * Residual (ba): every information asset has a twin substrate of LLM/operator
 * notes. Residual (cq): autoLoad twins on mount for DR/hosted windows.
 * HTML-first; never PDF.
 */

import { useCallback, useEffect, useState } from "react";
import {
  fetchTwinNotes,
  promoteTwinsToContext,
  recordTwinNote,
  type TwinNotesResponse,
  type TwinPromoteContextResponse,
} from "../../api/engagement";

export type TwinNotesPanelProps = {
  assetId: string;
  spawnId?: string | null;
  /** Residual (cq): fetch twin notes on mount. */
  autoLoad?: boolean;
};

export function TwinNotesPanel({
  assetId,
  spawnId = null,
  autoLoad = false,
}: TwinNotesPanelProps) {
  const [twins, setTwins] = useState<TwinNotesResponse | null>(null);
  const [promoted, setPromoted] = useState<TwinPromoteContextResponse | null>(
    null,
  );
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

  useEffect(() => {
    if (!autoLoad || !assetId.trim()) return;
    void load();
    // Mount-once per asset when autoLoad is on (residual cq).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoLoad, assetId]);

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

  const promote = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const p = await promoteTwinsToContext({
        asset_id: assetId,
        include_html: true,
      });
      if (p.view_format !== "html") {
        throw new Error("twin promote view_format must be html");
      }
      setPromoted(p);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, [assetId]);

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
        <button
          type="button"
          data-testid="twin-promote-context"
          onClick={() => void promote()}
          disabled={busy}
          title="Promote twins into research context units"
        >
          Promote to context
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
            <div
              data-testid="twin-notes-html"
              dangerouslySetInnerHTML={{ __html: twins.html }}
            />
          ) : null}
        </div>
      ) : null}
      {promoted ? (
        <div
          data-testid="twin-promote-result"
          data-view-format="html"
          className="font-mono text-sm"
        >
          <p>
            promoted={promoted.promoted_count} · context_units=
            {promoted.context_unit_count}
          </p>
          <ul data-testid="twin-promote-units">
            {promoted.context_units.map((u) => (
              <li key={u.unit_id}>
                <strong>[{u.kind}]</strong> {u.text}
              </li>
            ))}
          </ul>
          {promoted.notes?.map((n) => (
            <p key={n} className="meta">
              {n}
            </p>
          ))}
          {promoted.html ? (
            <div
              data-testid="twin-promote-html"
              dangerouslySetInnerHTML={{ __html: promoted.html }}
            />
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

export default TwinNotesPanel;
