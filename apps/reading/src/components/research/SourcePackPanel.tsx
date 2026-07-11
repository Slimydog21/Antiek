/**
 * SourcePackPanel — deep-research source pack UI (arxiv/substack/web/corpus).
 *
 * Free-file. Does not live-fetch; advisory pack only.
 */

import { useState } from "react";
import { LemonButton, LemonCard } from "../lemon";
import {
  formatSourcePackSummary,
  parseSourcePackResult,
  postSourcePack,
  type SourcePackResult,
} from "../../api/sourcePack";

const SOURCES = ["arxiv", "substack", "web", "operator_corpus"] as const;

export interface SourcePackPanelProps {
  buildFn?: (
    req: Parameters<typeof postSourcePack>[0],
  ) => Promise<SourcePackResult | unknown>;
  initialSelected?: string[];
}

export default function SourcePackPanel({
  buildFn = postSourcePack,
  initialSelected = ["arxiv", "substack"],
}: SourcePackPanelProps) {
  const [selected, setSelected] = useState<Set<string>>(
    () => new Set(initialSelected),
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<SourcePackResult | null>(null);

  function toggle(src: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(src)) next.delete(src);
      else next.add(src);
      return next;
    });
  }

  async function onBuild() {
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const raw = await buildFn({ selected: Array.from(selected) });
      setResult(parseSourcePackResult(raw));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div data-testid="source-pack-panel">
      <LemonCard title="Deep research source pack" className="source-pack-panel">
        <p className="text-sm opacity-80" data-testid="source-pack-blurb">
          Choose knowledge-dense sources (arXiv, Substack, web, operator corpus)
          for deep research. Builds an advisory pack only — no live fetch.
        </p>
        <div className="flex flex-col gap-2 mt-3">
          {SOURCES.map((src) => (
            <label key={src} className="text-sm flex items-center gap-2">
              <input
                type="checkbox"
                checked={selected.has(src)}
                onChange={() => toggle(src)}
                data-testid={`source-pack-toggle-${src}`}
                disabled={busy}
              />
              {src}
            </label>
          ))}
          <LemonButton
            variant="primary"
            disabled={busy}
            onClick={() => void onBuild()}
            data-testid="source-pack-build"
          >
            {busy ? "Building…" : "Build source pack"}
          </LemonButton>
          {error ? (
            <div className="text-sm text-danger" data-testid="source-pack-error">
              {error}
            </div>
          ) : null}
          {result ? (
            <div data-testid="source-pack-result" className="flex flex-col gap-2">
              <div data-testid="source-pack-summary">
                {formatSourcePackSummary(result)}
              </div>
              <pre
                className="max-h-48 overflow-auto text-xs rounded border border-border p-2"
                data-testid="source-pack-text"
              >
                {result.pack_text}
              </pre>
            </div>
          ) : null}
        </div>
      </LemonCard>
    </div>
  );
}
