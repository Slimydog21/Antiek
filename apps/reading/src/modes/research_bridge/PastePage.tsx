/**
 * PastePage — the front door of the Deep Research Bridge.
 *
 * The operator drops a deep-research output into the textarea. As
 * they type/paste, a debounced detection preview (no write) shows
 * the provider the bridge thinks it is — and, when ambiguous, the
 * per-source scores so the operator can override before committing.
 * On save, the paste lands and the recent-pastes shelf refreshes.
 *
 * Design decisions that are load-bearing:
 *
 *  - Detection preview is BEFORE commit, not after. The operator
 *    sees + can correct the source while the text is in front of
 *    them. Detecting after the row is written would force a separate
 *    correction round-trip.
 *  - The source override defaults to the detected source, not to a
 *    blank dropdown. The common case (detection is right) is one
 *    click — Save. The uncommon case (override) is still one extra
 *    click. We never make the common case pay for the rare one.
 *  - After a successful save we offer the immediate next action —
 *    "Extract now" — because the paste→extract→gap-find loop is the
 *    whole point. A dead-end "saved!" toast would make the operator
 *    hunt for what to do next.
 */

import { useCallback, useMemo, useState } from "react";
import {
  LemonButton, LemonCard, LemonInput, LemonSelect, LemonTag, LemonTextarea, toast,
} from "../../components/lemon";
import { BlockShelf } from "./BlockShelf";
import type { ResearchBridgeClient } from "./api_client";
import { useDetect, usePastes, usePostPaste, useExtract } from "./hooks";
import { ALL_SOURCES, SOURCE_VISUAL } from "./types";
import type { ResearchSource } from "./types";

export interface PastePageProps {
  client: ResearchBridgeClient;
  /** Optional default session for new pastes. */
  initialSessionId?: string | null;
  /** Called after a paste lands — e.g. to route to the gap-finder. */
  onPasteSaved?: (documentId: string) => void;
  className?: string;
}

export function PastePage({
  client, initialSessionId = null, onPasteSaved, className,
}: PastePageProps) {
  const pastes = usePastes({ client });
  const detector = useDetect(client);
  const poster = usePostPaste(client);
  const extractor = useExtract(client);

  const [draft, setDraft] = useState("");
  const [operatorLabel, setOperatorLabel] = useState("");
  const [sessionId, setSessionId] = useState(initialSessionId ?? "");
  // null = "use detected source"; otherwise an explicit override.
  const [override, setOverride] = useState<ResearchSource | "__auto__">("__auto__");
  const [lastSavedDoc, setLastSavedDoc] = useState<string | null>(null);

  const handleDraftChange = useCallback((value: string) => {
    setDraft(value);
    detector.detect(value);
    if (lastSavedDoc) setLastSavedDoc(null);
  }, [detector, lastSavedDoc]);

  const detected = detector.state.kind === "ok" ? detector.state.data : null;
  // The source that WILL be used on save: explicit override wins,
  // else the detected source, else 'other' until detection lands.
  const effectiveSource: ResearchSource =
    override !== "__auto__" ? override : (detected?.source ?? "other");

  const canSave = draft.trim().length > 0 && poster.state.kind !== "loading";

  const onSave = useCallback(async () => {
    if (!canSave) return;
    try {
      const result = await poster.post({
        raw_text: draft,
        operator_label: operatorLabel.trim() || null,
        session_id: sessionId.trim() || null,
        source_override: override === "__auto__" ? null : override,
      });
      setLastSavedDoc(result.document_id);
      setDraft("");
      detector.reset();
      setOverride("__auto__");
      void pastes.refresh();
      toast.ok(`Saved as ${SOURCE_VISUAL[result.source].label}`);
      onPasteSaved?.(result.document_id);
    } catch (e) {
      toast.err(`Save failed: ${(e as Error).message}`);
    }
  }, [canSave, draft, operatorLabel, sessionId, override, poster, detector, pastes, onPasteSaved]);

  const onExtractLast = useCallback(async () => {
    if (!lastSavedDoc) return;
    try {
      const r = await extractor.extract(lastSavedDoc);
      toast.ok(`Extracted ${r.insights.length} insight${r.insights.length === 1 ? "" : "s"} + ${r.open_questions.length} open Q`);
      void pastes.refresh();
    } catch (e) {
      toast.err(`Extract failed: ${(e as Error).message}`);
    }
  }, [lastSavedDoc, extractor, pastes]);

  const detectionBanner = useMemo(() => {
    if (draft.trim().length === 0) return null;
    if (detector.state.kind === "loading") {
      return <span className="text-shadow-2 dark:text-moonlight">detecting…</span>;
    }
    if (detector.state.kind === "ok") {
      const d = detector.state.data;
      const isOther = d.source === "other";
      return (
        <span className="flex items-center gap-2">
          <span className="text-shadow-2 dark:text-moonlight">detected</span>
          <LemonTag colour={SOURCE_VISUAL[d.source].tagColour}>
            {SOURCE_VISUAL[d.source].label} · {Math.round(d.confidence * 100)}%
          </LemonTag>
          {isOther && (
            <span className="text-xs text-shadow-2 dark:text-moonlight">
              (ambiguous — pick a source below, or save as Other)
            </span>
          )}
        </span>
      );
    }
    return null;
  }, [draft, detector.state]);

  const shelfBlocks = pastes.state.kind === "ok" ? pastes.state.data.pastes : [];

  return (
    <div
      className={[
        "grid grid-cols-1 lg:grid-cols-[1fr_minmax(0,360px)] gap-4 h-full",
        className ?? "",
      ].filter(Boolean).join(" ")}
    >
      {/* LEFT — paste form */}
      <div className="flex flex-col gap-3 min-h-[400px]">
        <LemonCard
          elevation="z2" colour="card"
          title={<span className="font-bold">Paste deep research</span>}
        >
          <div className="flex flex-col gap-2">
            <div className="text-xs text-shadow-2 dark:text-moonlight">
              Drop a deep-research output from ChatGPT, Anthropic, Grok, or
              AlphaSense. The raw text is preserved verbatim; insights and
              open questions are extracted on demand.
            </div>
            <LemonTextarea
              placeholder="Paste the full deep-research output here…"
              value={draft}
              onChange={(e) => handleDraftChange(e.target.value)}
              rows={16}
              aria-label="Paste textarea"
            />
            <div className="flex items-center gap-2 min-h-[28px] text-sm">
              {detectionBanner}
            </div>
            <div className="flex flex-wrap gap-2 items-center">
              <LemonInput
                placeholder="Label (optional)"
                value={operatorLabel}
                onChange={(e) => setOperatorLabel(e.target.value)}
                aria-label="Operator label"
              />
              <LemonInput
                placeholder="Session id (optional)"
                value={sessionId}
                onChange={(e) => setSessionId(e.target.value)}
                aria-label="Session id"
              />
              <LemonSelect
                value={override}
                onChange={(v) => setOverride(v as ResearchSource | "__auto__")}
                options={[
                  { value: "__auto__", label: detected ? `Auto (${SOURCE_VISUAL[detected.source].label})` : "Auto-detect" },
                  ...ALL_SOURCES.map((s) => ({ value: s, label: SOURCE_VISUAL[s].label })),
                ]}
                aria-label="Source override"
              />
            </div>
            <div className="flex items-center gap-2">
              <LemonButton
                size="md" variant="primary" onClick={onSave} disabled={!canSave}
              >
                {poster.state.kind === "loading"
                  ? "Saving…"
                  : `Save as ${SOURCE_VISUAL[effectiveSource].label}`}
              </LemonButton>
              {lastSavedDoc && (
                <LemonButton
                  size="md" variant="secondary" onClick={onExtractLast}
                  disabled={extractor.state.kind === "loading"}
                >
                  {extractor.state.kind === "loading" ? "Extracting…" : "Extract now"}
                </LemonButton>
              )}
            </div>
            {lastSavedDoc && (
              <div className="text-xs text-shadow-2 dark:text-moonlight">
                Saved <code>{lastSavedDoc.slice(0, 22)}…</code>. Extract now to
                pull insights + open questions, or batch-extract later.
              </div>
            )}
          </div>
        </LemonCard>
      </div>

      {/* RIGHT — recent pastes */}
      <div className="flex flex-col gap-2 min-h-[400px]">
        <div className="text-xs uppercase tracking-wide font-bold text-shadow-2 dark:text-moonlight">
          Recent pastes
        </div>
        {pastes.state.kind === "loading" && (
          <LemonCard elevation="z1" colour="glacial">
            <div className="text-sm">Loading…</div>
          </LemonCard>
        )}
        {pastes.state.kind === "error" && (
          <LemonCard elevation="z1" colour="card">
            <div className="text-sm text-emperor">
              Couldn't load pastes: {pastes.state.error.message}
            </div>
          </LemonCard>
        )}
        {pastes.state.kind === "ok" && (
          <BlockShelf blocks={shelfBlocks} />
        )}
      </div>
    </div>
  );
}
