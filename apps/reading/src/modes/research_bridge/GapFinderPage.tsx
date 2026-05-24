/**
 * GapFinderPage — the cascade-prompt operator surface. Two-pane state
 * machine: scope-picker (left, BlockShelf multi-select) → Find Gaps →
 * clusters + ordered PromptCards (right). Composes hooks + kit; owns
 * no domain state beyond scope-picker form fields.
 */

import { useCallback, useMemo, useState } from "react";
import { LemonButton, LemonCard, LemonInput, LemonTag } from "../../components/lemon";
import { BlockShelf } from "./BlockShelf";
import { PromptCard } from "./PromptCard";
import type { ResearchBridgeClient } from "./api_client";
import { useFindGaps, usePastes, usePasteBack, useSignals } from "./hooks";

export interface GapFinderPageProps {
  client: ResearchBridgeClient;
  initialSessionId?: string | null;
  initialScope?: string[];
  className?: string;
}

export function GapFinderPage({
  client, initialSessionId = null, initialScope, className,
}: GapFinderPageProps) {
  const pastes = usePastes({ client });
  const gaps = useFindGaps(client);
  const signals = useSignals(client);
  const pasteBack = usePasteBack(client);

  const [selectedIds, setSelectedIds] = useState<Set<string>>(
    () => new Set(initialScope ?? []),
  );
  const [operatorLabel, setOperatorLabel] = useState<string>("");
  const [sessionId, setSessionId] = useState<string>(initialSessionId ?? "");

  const scope = useMemo(() => Array.from(selectedIds), [selectedIds]);

  const onFindGaps = useCallback(async () => {
    if (scope.length === 0) return;
    try {
      await gaps.find({
        scope_block_ids: scope,
        operator_label: operatorLabel.trim() || null,
        session_id: sessionId.trim() || null,
      });
    } catch {
      // gaps.state carries the error; page reads from state.
    }
  }, [scope, operatorLabel, sessionId, gaps]);

  const onPasteBack = useCallback(
    async (prompt: Parameters<typeof pasteBack.pasteBack>[0], rawText: string) => {
      const result = await pasteBack.pasteBack(prompt, rawText, sessionId.trim() || null);
      void pastes.refresh();
      return result;
    },
    [pasteBack, pastes, sessionId],
  );

  const onReFindGaps = useCallback(async () => {
    if (gaps.state.kind !== "ok") return;
    try {
      await gaps.find({
        scope_block_ids: gaps.state.data.run.scope_block_ids,
        operator_label: gaps.state.data.run.operator_label,
        session_id: gaps.state.data.run.session_id,
      });
    } catch {
      // see onFindGaps.
    }
  }, [gaps]);

  const shelfBlocks = pastes.state.kind === "ok" ? pastes.state.data.pastes : [];
  const pageBusy = gaps.state.kind === "loading" || pasteBack.state.kind === "loading";

  return (
    <div
      className={[
        "grid grid-cols-1 lg:grid-cols-[minmax(0,360px)_1fr] gap-4 h-full",
        className ?? "",
      ].filter(Boolean).join(" ")}
    >
      {/* LEFT — scope picker */}
      <div className="flex flex-col gap-3 min-h-[400px]">
        <LemonCard elevation="z2" colour="card" title={<span className="font-bold">Scope</span>}>
          <div className="flex flex-col gap-2">
            <div className="text-xs text-shadow-2 dark:text-moonlight">
              Select the pastes whose open questions should drive this run.
              Gap-finding works best across 3+ blocks.
            </div>
            <LemonInput
              placeholder="Operator label (optional)"
              value={operatorLabel}
              onChange={(e) => setOperatorLabel(e.target.value)}
              aria-label="Operator label for this run"
            />
            <LemonInput
              placeholder="Session id (optional)"
              value={sessionId}
              onChange={(e) => setSessionId(e.target.value)}
              aria-label="Session id"
            />
            <div className="flex items-center gap-2">
              <LemonTag colour={scope.length >= 3 ? "sun" : "muted"}>
                {scope.length} selected
              </LemonTag>
              <LemonButton
                size="sm" variant="primary" onClick={onFindGaps}
                disabled={scope.length === 0 || pageBusy}
              >
                {gaps.state.kind === "loading" ? "Finding gaps…" : "Find gaps"}
              </LemonButton>
            </div>
            {pastes.state.kind === "error" && (
              <div className="text-xs text-emperor">
                Couldn't load pastes: {pastes.state.error.message}
              </div>
            )}
          </div>
        </LemonCard>

        <div className="flex-1 min-h-0">
          {pastes.state.kind === "loading" && (
            <LemonCard elevation="z1" colour="glacial">
              <div className="text-sm">Loading pastes…</div>
            </LemonCard>
          )}
          {pastes.state.kind === "ok" && shelfBlocks.length === 0 && (
            <LemonCard elevation="z1" colour="glacial">
              <div className="text-sm">
                No pastes yet. Paste a deep-research output via{" "}
                <code>/research/pastes</code> to seed the bridge.
              </div>
            </LemonCard>
          )}
          {pastes.state.kind === "ok" && shelfBlocks.length > 0 && (
            <BlockShelf
              blocks={shelfBlocks} multiSelect
              selectedIds={selectedIds} onSelectionChange={setSelectedIds}
            />
          )}
        </div>
      </div>

      {/* RIGHT — run output */}
      <div className="flex flex-col gap-3 min-h-[400px]">
        {gaps.state.kind === "idle" && (
          <LemonCard elevation="z2" colour="glacial">
            <div className="text-sm text-shadow-2 dark:text-moonlight">
              No gap-finder run yet. Pick pastes on the left and click
              <strong> Find gaps</strong>. The substrate caches results, so
              re-running with the same scope is cheap.
            </div>
          </LemonCard>
        )}
        {gaps.state.kind === "loading" && (
          <LemonCard elevation="z2" colour="sun">
            <div className="text-sm font-medium">Running clusterer + cascade generator…</div>
            <div className="text-xs text-shadow-2 dark:text-moonlight mt-1">
              Two LLM calls. Cluster step assigns questions to ≤7 themed
              groups; cascade step writes provider-routed prompts in order.
            </div>
          </LemonCard>
        )}
        {gaps.state.kind === "error" && (
          <LemonCard elevation="z2" colour="card">
            <div className="text-sm text-emperor">Gap-finder error: {gaps.state.error.message}</div>
            <div className="mt-2">
              <LemonButton size="sm" variant="primary" onClick={onFindGaps}>Retry</LemonButton>
            </div>
          </LemonCard>
        )}
        {gaps.state.kind === "ok" && (
          <>
            <LemonCard
              elevation="z2" colour="card"
              title={
                <div className="flex items-center gap-2">
                  <span className="font-bold">Run</span>
                  <code className="text-xs">{gaps.state.data.run.run_id}</code>
                  <span className="ml-auto flex gap-2">
                    <LemonTag colour="muted">
                      {gaps.state.data.clusters.length} cluster
                      {gaps.state.data.clusters.length === 1 ? "" : "s"}
                    </LemonTag>
                    <LemonTag colour="muted">
                      {gaps.state.data.prompts.length} prompt
                      {gaps.state.data.prompts.length === 1 ? "" : "s"}
                    </LemonTag>
                    {gaps.state.data.grounding_drops > 0 && (
                      <LemonTag colour="danger">
                        {gaps.state.data.grounding_drops} grounding drops
                      </LemonTag>
                    )}
                    <LemonTag colour="muted">
                      ${gaps.state.data.run.total_cost_usd.toFixed(4)}
                    </LemonTag>
                  </span>
                </div>
              }
              footer={
                <div className="flex gap-2">
                  <LemonButton size="sm" variant="secondary" onClick={onReFindGaps}>
                    Re-find gaps (same scope)
                  </LemonButton>
                </div>
              }
            >
              {gaps.state.data.clusters.length === 0 ? (
                <div className="text-sm text-shadow-2 dark:text-moonlight">
                  No clusters formed. Either the scope had no open questions
                  yet, or the model declined to group them. Try adding more
                  blocks to the scope.
                </div>
              ) : (
                <div className="flex flex-col gap-1.5">
                  {gaps.state.data.clusters.map((c) => (
                    <div key={c.cluster_id} className="text-sm">
                      <span className="font-mono text-xs px-1.5 py-0.5 mr-2 rounded bg-ice-3 dark:bg-charcoal-1">
                        #{c.priority_rank}
                      </span>
                      <span className="font-medium">{c.label}</span>
                      {c.rationale && (
                        <span className="text-xs text-shadow-2 dark:text-moonlight ml-2">
                          — {c.rationale}
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </LemonCard>

            {gaps.state.data.prompts.length > 0 && (
              <div className="flex flex-col gap-2">
                <div className="text-xs uppercase tracking-wide font-bold text-shadow-2 dark:text-moonlight">
                  Run prompts in order
                </div>
                {gaps.state.data.prompts.map((p) => (
                  <PromptCard
                    key={p.prompt_id}
                    prompt={p}
                    currentSignal={signals.signals[p.prompt_id]}
                    signalError={signals.errors[p.prompt_id]}
                    onSignal={signals.setSignal}
                    onPasteBack={onPasteBack}
                  />
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
