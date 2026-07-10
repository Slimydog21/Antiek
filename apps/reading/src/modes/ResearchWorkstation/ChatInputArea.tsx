import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { DecisionTreeDriverBadge } from "../../components/engagement/DecisionTreeDriverBadge";
import {
  ResearchLaunchBudgetPanel,
  type ResearchLaunchBudgetProjection,
} from "../../components/engagement/ResearchLaunchBudgetPanel";
import LemonButton from "../../components/lemon/LemonButton";
import LemonTextarea from "../../components/lemon/LemonTextarea";
import { fetchDepthTiers } from "../../api/settings";
import { track, trackException } from "../../lib/analytics";
import { startInvestigation } from "../../lib/api";
import type { ResearchTier } from "../../lib/api";
import { mapDepthTierToResearchTier } from "../../lib/researchTier";
import {
  composeDriverPromptText,
  countPublicationRefs,
} from "../../lib/driverPromptText";
import {
  hydratePublicationRefs,
  parsePublicationRefs,
  questionWithPublicationRefs,
} from "./publicationRefs";
import { KNOWLEDGE_DENSE_PUBLICATION_PRESETS } from "../../components/engagement/PublicationAttachPanel";

/**
 * Bottom-of-center chat input. Submit on Cmd/Ctrl+Enter; click "Ask"
 * via the button at the right. POST /investigations + (by default)
 * navigate to `/inv/<id>`.
 *
 *   parentInvestigationId   if present, child-of-parent context is set
 *   spawnContext            the original highlight (chase-this)
 *   placeholder             override the placeholder text
 *   autoFocus               steal focus on mount
 *   onSubmitted             called with the new investigation_id;
 *                           when omitted, the component navigates itself
 *   researchTier           optional fast|deep|wrestle for launch + budget (default deep)
 * Residual (gr): budget-panel tier pick is written into startInvestigation
 * research_tier (not projection-only).
 * Residual (gu): Settings depth-tier prefill when prop is default deep.
 *
 * S5 redesign: now a Lemon-styled docked-bottom panel surface. The
 * surrounding chrome (sun-yellow border, ink offset shadow) is provided
 * by PanelLayoutPanel; this component renders only the inner controls.
 *
 * Residual (bq): live budget + #440 projection (parity with StartResearch bp).
 * Residual (ct): publication refs (arxiv/substack/url) parity with StartResearch cj.
 * Residual (agz): knowledge-dense quick-call presets on chase follow-ups
 * (parity StartResearch agy · mid-session attach agx).
 * Residual (df): soft-gate Ask when budget projection would exceed (parity de).
 * Residual (ln): DecisionTreeDriverBadge with launchTier (parity StartResearch ll).
 * Residual (qp): DecisionTreeDriverBadge promptText = question + pub refs.
 * Residual (qr): budget panel shares composeDriverPromptText (badge ≡ budget).
 * Residual (ahh): budget foresight pub-ref count stamps (parity StartResearch ahg).
 */
export default function ChatInputArea({
  parentInvestigationId,
  spawnContext,
  placeholder,
  autoFocus,
  onSubmitted,
  researchTier = "deep",
}: {
  parentInvestigationId?: string;
  spawnContext?: string;
  placeholder?: string;
  autoFocus?: boolean;
  onSubmitted?: (investigationId: string) => void;
  researchTier?: ResearchTier;
}) {
  const [question, setQuestion] = useState(spawnContext ?? "");
  const [pubRefs, setPubRefs] = useState("");
  const [pubRefStatus, setPubRefStatus] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [budgetWarn, setBudgetWarn] = useState(false);
  const [forceOverBudget, setForceOverBudget] = useState(false);
  // Residual (gr): launch tier state — prop default + budget-panel pick.
  const [launchTier, setLaunchTier] = useState<ResearchTier>(researchTier);
  const [depthPrefill, setDepthPrefill] = useState<
    "pending" | "settings" | "prop" | "default" | "error"
  >("pending");
  const navigate = useNavigate();

  // Keep prop → state in sync when parent remounts with a non-default prop.
  useEffect(() => {
    if (researchTier !== "deep") {
      setLaunchTier(researchTier);
      setDepthPrefill("prop");
    }
  }, [researchTier]);

  // Residual (gu): Settings depth-tier when prop is default deep.
  useEffect(() => {
    if (researchTier !== "deep") return;
    let cancelled = false;
    void fetchDepthTiers()
      .then((resp) => {
        if (cancelled) return;
        const mapped = mapDepthTierToResearchTier(resp.active_depth_tier);
        if (mapped) {
          setLaunchTier(mapped);
          setDepthPrefill("settings");
        } else {
          setDepthPrefill("default");
        }
      })
      .catch(() => {
        if (!cancelled) setDepthPrefill("error");
      });
    return () => {
      cancelled = true;
    };
  }, [researchTier]);

  const onProjectionChange = useCallback((p: ResearchLaunchBudgetProjection) => {
    setBudgetWarn(p.wouldExceedBudget === true);
  }, []);

  const submit = useCallback(async () => {
    const q = question.trim();
    if (!q || q.length < 3) {
      setError("Question is too short. At least 3 characters.");
      return;
    }
    if (budgetWarn && !forceOverBudget) {
      setError(
        "Projected cost may exceed remaining daily budget — enable force override or reduce scope.",
      );
      return;
    }
    setBusy(true);
    setError(null);
    setPubRefStatus(null);
    try {
      const refs = parsePublicationRefs(pubRefs);
      let launchQuestion = q;
      if (refs.length > 0) {
        const hydrated = await hydratePublicationRefs(refs);
        setPubRefStatus(
          `Hydrated ${hydrated.ok.length} publication asset(s)` +
            (hydrated.failed.length ? ` · ${hydrated.failed.length} failed` : "") +
            " · HTML-first",
        );
        launchQuestion = questionWithPublicationRefs(q, refs);
      }
      const resp = await startInvestigation({
        question: launchQuestion,
        parent_investigation_id: parentInvestigationId,
        spawn_context: spawnContext,
        // Residual (gr): wrestle|fast|deep from budget picker / prop.
        research_tier: launchTier,
      });
      track("investigation_started", {
        question_length: launchQuestion.length,
        has_parent: Boolean(parentInvestigationId),
        has_spawn_context: Boolean(spawnContext),
        publication_ref_count: refs.length,
        research_tier: launchTier,
      });
      setQuestion("");
      if (onSubmitted) {
        onSubmitted(resp.investigation_id);
      } else {
        navigate(`/inv/${resp.investigation_id}`);
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      trackException(e instanceof Error ? e : new Error(msg));
      setError(`Submit failed: ${msg}`);
    } finally {
      setBusy(false);
    }
  }, [
    question,
    pubRefs,
    parentInvestigationId,
    spawnContext,
    navigate,
    onSubmitted,
    budgetWarn,
    forceOverBudget,
    launchTier,
  ]);

  return (
    <div className="h-full flex flex-col p-3 bg-ice-1 dark:bg-charcoal-2 text-ink dark:text-bright">
      <div className="flex-1 min-h-0 flex flex-col">
        <LemonTextarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onSubmit={() => void submit()}
          placeholder={placeholder ?? "What do you want to research?"}
          autoFocus={autoFocus}
          disabled={busy}
          minRows={2}
          maxRows={10}
          className="font-serif text-[15px] leading-relaxed"
        />
        {error && (
          <div className="text-xs font-mono text-emperor mt-2">{error}</div>
        )}
      </div>
      {/* Residual (ct/agz): arxiv/substack/URL handles for chase follow-ups. */}
      <div
        className="mt-2 space-y-1"
        data-testid="chat-input-publication-refs"
        data-view-format="html"
        data-seamless-pub-quick-call="true"
        data-knowledge-dense-presets={String(
          KNOWLEDGE_DENSE_PUBLICATION_PRESETS.length,
        )}
      >
        <label
          className="text-[10px] font-mono uppercase tracking-wider text-ink-mute dark:text-moonlight"
          htmlFor="chat-publication-refs-input"
        >
          Publication refs
        </label>
        {/* Residual (agz): chase follow-up quick-call (parity agy launch · agx attach). */}
        <div
          className="flex flex-wrap gap-1 items-center"
          data-testid="chat-input-publication-quick-call"
          data-preset-count={String(KNOWLEDGE_DENSE_PUBLICATION_PRESETS.length)}
          data-seamless-pub-quick-call="true"
          data-auto-hydrate="false"
          role="group"
          aria-label="Knowledge-dense publication quick-call presets"
        >
          <span className="text-[10px] font-mono opacity-70 mr-1">Quick-call:</span>
          {KNOWLEDGE_DENSE_PUBLICATION_PRESETS.map((p) => (
            <button
              key={p.id}
              type="button"
              data-testid={`chat-input-preset-${p.id}`}
              data-preset-id={p.id}
              data-kind={p.kind}
              data-reference={p.reference}
              data-auto-hydrate="false"
              disabled={busy}
              onClick={() => {
                const ref = p.reference.trim();
                if (!ref) return;
                setPubRefs((prev) => {
                  const existing = new Set(
                    prev
                      .split(/\r?\n/)
                      .map((l) => l.trim())
                      .filter(Boolean),
                  );
                  if (existing.has(ref)) return prev;
                  const base = prev.trim();
                  return base ? `${base}\n${ref}` : ref;
                });
              }}
              className="text-[10px] font-mono border rounded px-1.5 py-0.5 opacity-80 hover:opacity-100 disabled:opacity-50 border-ink/20 dark:border-bright/20"
              title={`Insert ${p.reference} (hydrates offline-honest on Ask · never auto-live)`}
            >
              {p.label}
            </button>
          ))}
        </div>
        <textarea
          id="chat-publication-refs-input"
          data-testid="chat-publication-refs-input"
          value={pubRefs}
          onChange={(e) => setPubRefs(e.target.value)}
          disabled={busy}
          rows={2}
          placeholder={"arxiv:1706.03762\nhttps://…"}
          className="w-full rounded border border-ink/20 bg-transparent px-2 py-1 text-[11px] font-mono dark:border-bright/20"
        />
        {/* Residual (agg): dual-gate L1/L2 prep deep-links (parity StartResearch agf). */}
        <nav
          className="flex flex-wrap gap-3 text-[10px] font-mono"
          data-testid="chat-input-pub-refs-dual-gate"
          data-view-format="html"
          data-l1-arxiv="deferred"
          data-l2-substack="deferred"
          aria-label="Dual-gate checklist prep for arxiv and Substack hydrate"
        >
          <a
            href="/docs/campaigns/2026-07-09-research-reading-spine/DUAL-GATE-L1-L4-OPERATOR-CHECKLIST.md#l1-arxiv"
            data-testid="chat-input-l1-checklist-link"
            data-l1-arxiv="deferred"
            className="underline opacity-80 hover:opacity-100"
            title="L1 live arxiv body hydrate dual-gate checklist (offline identity default)"
          >
            L1 arxiv checklist
          </a>
          <a
            href="/docs/campaigns/2026-07-09-research-reading-spine/DUAL-GATE-L1-L4-OPERATOR-CHECKLIST.md#l2-substack"
            data-testid="chat-input-l2-checklist-link"
            data-l2-substack="deferred"
            className="underline opacity-80 hover:opacity-100"
            title="L2 live Substack body dual-gate checklist (offline identity default)"
          >
            L2 Substack checklist
          </a>
        </nav>
        {pubRefStatus ? (
          <p
            className="text-[10px] font-mono text-aurora"
            data-testid="chat-publication-refs-status"
            role="status"
          >
            {pubRefStatus}
          </p>
        ) : null}
      </div>
      {/* Residual (bq/df/ln/ahh): budget panel + driver badge · pub-ref foresight. */}
      <div
        className="mt-2"
        data-testid="chat-input-budget-mount"
        data-depth-prefill={depthPrefill}
        data-research-tier={launchTier}
        data-pub-ref-count={String(countPublicationRefs(pubRefs))}
        data-has-pub-refs={String(countPublicationRefs(pubRefs) > 0)}
        data-prompt-chars={String(
          composeDriverPromptText(question, pubRefs).length,
        )}
      >
        <div
          data-testid="chat-input-driver-badge-mount"
          data-view-format="html"
          data-research-tier={launchTier}
          data-pub-ref-count={String(countPublicationRefs(pubRefs))}
          data-has-pub-refs={String(countPublicationRefs(pubRefs) > 0)}
        >
          <DecisionTreeDriverBadge
            researchTier={launchTier}
            /* Residual (qp): question + pub refs cost foresight. */
            promptText={composeDriverPromptText(question, pubRefs)}
          />
        </div>
        <ResearchLaunchBudgetPanel
          promptText={composeDriverPromptText(question, pubRefs)}
          researchTier={launchTier}
          allowTierPick
          onResearchTierChange={setLaunchTier}
          onProjectionChange={onProjectionChange}
        />
        {budgetWarn ? (
          <label
            className="mt-1 flex items-center gap-2 text-[11px] font-mono text-emperor"
            data-testid="chat-input-over-budget-warn"
          >
            <input
              type="checkbox"
              data-testid="chat-input-force-over-budget"
              checked={forceOverBudget}
              onChange={(e) => setForceOverBudget(e.target.checked)}
              disabled={busy}
            />
            Force Ask despite budget projection
          </label>
        ) : null}
      </div>
      <div className="mt-2 flex items-center justify-between gap-3">
        <div className="text-[11px] font-mono text-ink-mute dark:text-moonlight">
          <kbd className="border-2 border-ink dark:border-bright rounded px-1.5 text-[10px] font-mono bg-ice-0 dark:bg-charcoal-1 shadow-[2px_2px_0_0_#0F1419] dark:shadow-[2px_2px_0_0_#8A7300] mr-1.5">⌘ ↵</kbd>
          to submit · live projection above
        </div>
        <LemonButton
          variant="primary"
          onClick={() => void submit()}
          disabled={
            busy ||
            question.trim().length < 3 ||
            (budgetWarn && !forceOverBudget)
          }
        >
          {busy ? "…" : "Ask"}
        </LemonButton>
      </div>
    </div>
  );
}
