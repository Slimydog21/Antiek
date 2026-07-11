/**
 * BookFreeCopyPanel — marketplace free-copy preflight UI.
 *
 * Before purchase intent: ask whether a free PD/OA copy exists.
 * Free-file: does not own Library/index, App.tsx, or purchase flows.
 */

import { useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../../components/lemon";
import {
  formatFreeCopySummary,
  parseFreeCopyPreflightResult,
  postFreeCopyPreflight,
  type FreeCopyPreflightResult,
} from "../../api/bookFreeCopy";

export interface BookFreeCopyPanelProps {
  preflightFn?: (
    req: Parameters<typeof postFreeCopyPreflight>[0],
  ) => Promise<FreeCopyPreflightResult | unknown>;
  initialTitle?: string;
  initialAuthor?: string;
}

export default function BookFreeCopyPanel({
  preflightFn = postFreeCopyPreflight,
  initialTitle = "",
  initialAuthor = "",
}: BookFreeCopyPanelProps) {
  const [title, setTitle] = useState(initialTitle);
  const [author, setAuthor] = useState(initialAuthor);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<FreeCopyPreflightResult | null>(null);

  async function onPreflight() {
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const raw = await preflightFn({
        title: title.trim(),
        author: author.trim() || null,
      });
      setResult(parseFreeCopyPreflightResult(raw));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div data-testid="book-free-copy-panel">
      <LemonCard title="Free-copy preflight" className="book-free-copy-panel">
        <p className="text-sm opacity-80" data-testid="book-free-copy-blurb">
          Search public-domain / open-access sources for a free copy before any
          purchase intent. If none is found, a buy-and-host path can be
          considered separately. This panel does not charge or purchase.
        </p>

        <div className="flex flex-col gap-3 mt-3">
          <label className="text-sm flex flex-col gap-1">
            <span>Title</span>
            <LemonInput
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Walden"
              data-testid="book-free-copy-title"
              aria-label="Book title"
              disabled={busy}
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Author (optional)</span>
            <LemonInput
              value={author}
              onChange={(e) => setAuthor(e.target.value)}
              placeholder="Thoreau"
              data-testid="book-free-copy-author"
              aria-label="Book author"
              disabled={busy}
            />
          </label>
          <LemonButton
            variant="primary"
            disabled={busy}
            onClick={() => void onPreflight()}
            data-testid="book-free-copy-run"
          >
            {busy ? "Searching…" : "Search free copies"}
          </LemonButton>

          {error ? (
            <div className="text-sm text-danger" data-testid="book-free-copy-error">
              {error}
            </div>
          ) : null}

          {result ? (
            <div data-testid="book-free-copy-result" className="flex flex-col gap-2">
              <div
                data-testid="book-free-copy-available"
                data-available={result.freely_available ? "true" : "false"}
              >
                {formatFreeCopySummary(result)}
              </div>
              {result.freely_available ? (
                <div data-testid="book-free-copy-source">
                  Source: {result.source}; rights: {result.rights_basis}
                </div>
              ) : (
                <ul
                  className="text-xs list-disc pl-4"
                  data-testid="book-free-copy-outcomes"
                >
                  {result.outcomes.map((o) => (
                    <li key={`${o.source}-${o.timestamp}`}>
                      {o.source}: {o.found ? "found" : "not found"}
                      {o.error ? ` (error: ${o.error})` : ""}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ) : null}
        </div>
      </LemonCard>
    </div>
  );
}
