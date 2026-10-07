/**
 * AgentPane.tsx — the agent second pane's Surface (SPR-07).
 *
 * STATE MACHINE (decision 5; refs pattern 7)
 *   closed ──openAgentPane──▶ opening ──mount──▶ open
 *   open ──Esc on root / × / drag past 244 px──▶ closing [linger 240 ms, root inert,
 *          data-closing: opacity .16 s + translate; reduced motion snaps]
 *   closing ──CLOSE_LINGER_MS──▶ closed  (companionStore.closeAgentTabWithUndo, 10 s Undo,
 *          then focus returns: the next visible companion tab's root, else [data-pane="left"])
 *
 * ESCAPE LADDER (refs pattern 10; composerKeys.nextEscapeRung)
 *   rung        where              what one Esc does
 *   picker      composer           closes the @/# listbox
 *   recording   composer           stops the (stub) recording
 *   chip        composer           removes the context chip, announces "Context removed"
 *   blur        composer           moves focus to the pane root ([data-agent-pane], tabIndex -1)
 *   close       root               closeAgentPane (the linger above)
 *   Every handled Esc is preventDefault + stopPropagation, so PanelLayout's
 *   fullscreen Escape owner never double-fires.
 *
 * Phase A: hosted standalone (the story and the vitest host); the registry
 * entry that mounts it under companion kind "agent" waits on F1 (Phase B).
 * Scope is enforced in this browser only (rigor #1): the server sees one
 * /thought-partner route with no project identity; the badge says so.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { parseAssistantReply, type AiAction } from "../../components/ai/aiActions";
import { getReadingFocus, READING_FOCUS_EVENT, type ReadingFocus } from "../../lib/readingFocus";
import { useContextTree } from "../contracts/treeStore";
import { useSelection } from "../contracts/selection";
import { anchorKey } from "../contracts/anchor";
import { useTabTrees } from "../tabTreeStore";
import { useTabTitles, titleKey } from "../tabTitles";
import { useCompanion } from "../companionStore";
import { usePrefersReducedMotion } from "../usePrefersReducedMotion";
import { isTextEditing } from "../shortcuts";
import { AgentComposer } from "./AgentComposer";
import { AgentEmptyState } from "./AgentEmptyState";
import { AgentReplyActions } from "./AgentReplyActions";
import { AgentThread } from "./AgentThread";
import { useAgentDraft } from "./agentDraft";
import { agentDraftKey } from "./agentPaneId";
import { CLOSE_LINGER_MS, closeAgentPane, useAgentPaneStore, useSyncProjectFilter } from "./agentPaneStore";
import { historyFor, useAgentThreads, type AgentTurn } from "./agentThreadStore";
import { agentSystemContext, failureReasonOf, projectTreeSummary, thoughtPartnerTransport, type AgentTransport, type AgentTransportReply } from "./agentTransport";
import { PANE, type AgentPaneTab } from "./agentTypes";
import { chipText, verifyQuoteAgainstFocus } from "./anchorContext";
import { serializeDraft, sourceCandidates, type ComposerChip } from "./composerChips";
import type { EscapeRung } from "./composerKeys";
import { INTERVIEW_FIRST_TURN, dispatchProjectSeed, parseOptionCard, type OptionCard } from "./interviewMode";
import { PaneHashSync, useInRouterContext } from "./paneHash";
import { simulateStream } from "./simulatedStream";
import { IDLE, createTurnRunner, type LifecycleState, type TurnRunner } from "./turnLifecycle";

export { CLOSE_LINGER_MS };

/** The sr-only status region announces after a short beat (refs pattern 2). */
const ANNOUNCE_DELAY_MS = 50;

export interface AgentPaneProps {
  tab: AgentPaneTab;
  /** The transport seam (fix 2); the thought-partner whole-reply transport by default. */
  transport?: AgentTransport;
  interview?: boolean;
  /** False while another companion tab is active (paste-anywhere is not installed). */
  active?: boolean;
  /** Observation seam for tests: every rung walked, "close" included. */
  onEscapeRung?: (rung: EscapeRung) => void;
}

const EMPTY_TURNS: readonly AgentTurn[] = Object.freeze([]);

function useReadingFocusLive(): ReadingFocus | null {
  const [focus, setFocus] = useState<ReadingFocus | null>(() => getReadingFocus());
  useEffect(() => {
    const onFocus = () => setFocus(getReadingFocus());
    window.addEventListener(READING_FOCUS_EVENT, onFocus);
    return () => window.removeEventListener(READING_FOCUS_EVENT, onFocus);
  }, []);
  return focus;
}

/** The open left reader tabs (the honest pre-tree source list). */
function useLeftReaderTabs(): { id: string; title: string }[] {
  const tree = useTabTrees((s) => s.trees.reading);
  const entries = useTabTitles((s) => s.entries);
  return useMemo(() => {
    if (!tree) return [];
    return Object.values(tree.nodes)
      .filter((n) => n.kind === "reader" && !n.pruned_at)
      .map((n) => {
        const entry = entries[titleKey(n.kind, n.ref)];
        return { id: n.ref, title: entry && entry.state === "known" && entry.title ? entry.title : n.ref };
      });
  }, [tree, entries]);
}

export function AgentPane({ tab, transport = thoughtPartnerTransport, interview = false, active = true, onEscapeRung }: AgentPaneProps) {
  const rootRef = useRef<HTMLElement>(null);
  const key = tab.id;
  const turns = useAgentThreads((s) => s.threads[key]) ?? EMPTY_TURNS;
  const closing = useAgentPaneStore((s) => Boolean(s.closing[tab.id]));
  const recording = useAgentPaneStore((s) => Boolean(s.recording[tab.id]));
  const openNonce = useAgentPaneStore((s) => s.openNonce[tab.id] ?? 0);
  const chipDismissed = useAgentPaneStore((s) => s.chipDismissed[tab.id]);
  const reducedMotion = usePrefersReducedMotion();
  const focus = useReadingFocusLive();
  const tree = useContextTree();
  const selection = useSelection((s) => s.selection);
  const leftTabs = useLeftReaderTabs();
  const companionTabs = useCompanion((s) => s.tabs);
  const inRouter = useInRouterContext();

  useSyncProjectFilter();

  const draftKey = agentDraftKey({ ...(tab.projectId ? { projectId: tab.projectId } : {}), agentId: tab.agentId, pane: PANE });
  const [draft, setDraft] = useAgentDraft(draftKey);
  const [chips, setChips] = useState<ComposerChip[]>([]);
  const [lifecycle, setLifecycle] = useState<LifecycleState>(IDLE);
  const [status, setStatus] = useState("");
  const runnerRef = useRef<TurnRunner | null>(null);
  const streamCancel = useRef<() => void>(() => {});
  const announceTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const announce = useCallback((text: string) => {
    if (announceTimer.current !== null) clearTimeout(announceTimer.current);
    setStatus("");
    announceTimer.current = setTimeout(() => { announceTimer.current = null; setStatus(text); }, ANNOUNCE_DELAY_MS);
  }, []);

  // The anchor's quote, re-derived against the servable page (pattern 3 interim).
  const anchor = tab.anchor;
  const anchorId = anchor ? anchorKey(anchor) : null;
  const verification = useMemo(() => (anchor ? verifyQuoteAgainstFocus(anchor, focus) : null), [anchor, focus]);
  const chipVisible = Boolean(anchor && anchor.quoteHint && chipDismissed !== anchorId);
  const prevAnchorId = useRef(anchorId);
  useEffect(() => {
    if (anchorId !== prevAnchorId.current) {
      prevAnchorId.current = anchorId;
      if (anchorId && anchor?.quoteHint) announce(`Context: ${chipText(anchor.quoteHint)}`);
    }
  }, [anchorId, anchor, announce]);

  const candidates = useMemo(() => ({
    agents: companionTabs.filter((t) => t.id !== tab.id).map((t) => ({ id: t.id, label: t.title })),
    sources: sourceCandidates(tree, selection, leftTabs),
  }), [companionTabs, tab.id, tree, selection, leftTabs]);

  const systemContext = useCallback(() => agentSystemContext({
    projectSummary: tab.scope === "project" && tab.projectId ? projectTreeSummary(tree, tab.projectId) : null,
    scope: tab.scope,
    ...(tab.projectId ? { projectId: tab.projectId } : {}),
    focus,
    verifiedQuote: chipVisible && verification && verification.quote ? verification.quote : null,
    interview,
  }), [tab.scope, tab.projectId, tree, focus, chipVisible, verification, interview]);

  const finishTurn = useCallback((turnId: string, reply: AgentTransportReply) => {
    const { prose, actions } = parseAssistantReply(reply.text);
    const parsed = interview ? parseOptionCard(prose || reply.text) : { prose: prose || reply.text, card: null };
    const text = parsed.prose;
    const store = useAgentThreads.getState();
    streamCancel.current();
    streamCancel.current = simulateStream(text, (sofar, done) => {
      if (done) {
        store.completeTurn(key, turnId, {
          answer: sofar, shape: reply.shape, actions,
          ...(reply.libraryRetrievalStatus !== undefined ? { libraryRetrievalStatus: reply.libraryRetrievalStatus } : {}),
          ...(parsed.card ? { optionCard: parsed.card } : {}),
        });
        setLifecycle(IDLE);
      } else {
        store.streamTurn(key, turnId, sofar);
      }
    }, { reducedMotion });
  }, [interview, key, reducedMotion]);

  const send = useCallback((text: string, opts: { hidden?: boolean } = {}) => {
    const prompt = opts.hidden ? text : serializeDraft(chips, text.trim());
    if (!prompt) return;
    const store = useAgentThreads.getState();
    const turnId = store.startTurn(key, prompt, opts);
    runnerRef.current?.dispose();
    const runner = createTurnRunner({
      transport,
      request: () => ({ prompt, history: historyFor(useAgentThreads.getState().threads[key]), system_context: systemContext() }),
      onState: (s, reply) => {
        setLifecycle(s);
        if (s.phase === "done" && reply) finishTurn(turnId, reply);
        if (s.phase === "failed") useAgentThreads.getState().failTurn(key, turnId, s.error === null ? null : failureReasonOf(new Error(s.error)));
        if (s.phase === "sent") {
          const t = useAgentThreads.getState().threads[key]?.find((x) => x.id === turnId);
          if (t && t.status === "failed") useAgentThreads.getState().reopenTurn(key, turnId); // a retry re-opens the same turn
        }
      },
    });
    runnerRef.current = runner;
    runner.send();
    if (!opts.hidden) {
      setDraft("");
      setChips([]);
    }
  }, [chips, key, transport, systemContext, finishTurn, setDraft]);

  // The interview's hidden first turn, once per tab.
  const interviewStarted = useRef(false);
  useEffect(() => {
    if (!interview || interviewStarted.current || turns.length > 0) return;
    interviewStarted.current = true;
    send(INTERVIEW_FIRST_TURN, { hidden: true });
  }, [interview, turns.length, send]);

  // An inert surface holds no focus: the moment the linger starts, focus
  // leaves the root (the left pane, never <body>); closeAgentPane's own
  // focus return runs after the tab is gone.
  useEffect(() => {
    if (!closing) return;
    const root = rootRef.current;
    if (root && root.contains(document.activeElement)) {
      document.querySelector<HTMLElement>('[data-pane="left"]')?.focus();
      if (root.contains(document.activeElement)) (document.activeElement as HTMLElement | null)?.blur();
    }
  }, [closing]);

  useEffect(() => () => {
    runnerRef.current?.dispose();
    streamCancel.current();
    if (announceTimer.current !== null) clearTimeout(announceTimer.current);
  }, []);

  const close = useCallback(() => {
    onEscapeRung?.("close");
    closeAgentPane(tab.id, tab.title);
  }, [onEscapeRung, tab.id, tab.title]);

  const onRung = useCallback((rung: EscapeRung) => {
    if (rung === "recording") useAgentPaneStore.getState().setRecording(tab.id, false);
    if (rung === "chip" && anchorId) {
      useAgentPaneStore.getState().dismissChip(tab.id, anchorId);
      announce("Context removed");
    }
    onEscapeRung?.(rung);
  }, [tab.id, anchorId, announce, onEscapeRung]);

  const onRootKeyDown = (e: React.KeyboardEvent<HTMLElement>) => {
    if (e.key !== "Escape" || closing) return;
    const target = e.target instanceof Element ? e.target : null;
    if (target && target !== e.currentTarget && isTextEditing(target)) return;
    e.preventDefault();
    e.stopPropagation();
    close();
  };

  const visibleTurns = turns;
  const lastDone = [...turns].reverse().find((t) => t.status === "done");
  const actions: readonly AiAction[] = lastDone?.actions ?? [];
  const cards = useMemo(() => {
    if (!interview) return [] as { turnId: string; card: OptionCard; resolved: boolean }[];
    const out: { turnId: string; card: OptionCard; resolved: boolean }[] = [];
    turns.forEach((t, i) => {
      if (t.status === "done" && t.optionCard) out.push({ turnId: t.id, card: t.optionCard, resolved: i < turns.length - 1 });
    });
    return out;
  }, [interview, turns]);

  const scopeBadge = tab.scope === "project" ? `project ${tab.projectId ?? ""}` : "cross-project";

  return (
    <section
      ref={rootRef}
      data-agent-pane
      data-agent-id={tab.agentId}
      {...(closing ? { inert: "", "data-closing": "" } : {})}
      tabIndex={-1}
      aria-label="Agent"
      onKeyDown={onRootKeyDown}
      className={`flex flex-col h-full min-h-0 min-w-0 outline-none ${reducedMotion ? "" : "transition-[opacity,transform] duration-150"} ${closing ? "opacity-0 translate-x-2" : ""}`}
    >
      {inRouter ? <PaneHashSync agentId={tab.agentId} active={active && !closing} /> : null}
      <p role="status" aria-live="polite" className="sr-only">{status}</p>
      <header className="flex items-center gap-2 shrink-0 border-b border-hairline px-3 py-1.5">
        <span className="text-xs font-medium text-ink dark:text-bright truncate">{tab.title}</span>
        <span
          className="text-xxs font-mono rounded-full border border-hairline px-1.5 text-shadow-1 dark:text-moonlight"
          title="Scope enforced in this browser only"
          data-scope-badge
        >
          {scopeBadge}
        </span>
        <button
          type="button"
          className="ml-auto text-shadow-1 hover:text-bright px-1"
          aria-label="Close the agent pane (the agent itself is untouched)"
          onClick={close}
        >
          ×
        </button>
      </header>
      {chipVisible && anchor?.quoteHint ? (
        <div className="flex items-center gap-1 px-3 py-1 shrink-0" data-context-chip>
          <span className="text-xxs font-mono truncate text-ink-soft dark:text-moonlight" title={verification && verification.quote !== null ? "Verified against the open page" : `Not sent: ${verification ? verification.reason : "unverified"}`}>
            {chipText(anchor.quoteHint)}
          </span>
          <button
            type="button"
            aria-label="Remove the context"
            className="text-shadow-1 hover:text-bright px-1"
            onClick={() => {
              if (anchorId) useAgentPaneStore.getState().dismissChip(tab.id, anchorId);
              announce("Context removed");
              rootRef.current?.querySelector<HTMLTextAreaElement>("textarea")?.focus();
            }}
          >
            ×
          </button>
        </div>
      ) : null}
      {visibleTurns.length === 0 && !interview ? (
        <div className="flex-1 min-h-0 overflow-y-auto">
          <AgentEmptyState onPrompt={(text) => send(text)} />
        </div>
      ) : (
        <AgentThread
          turns={visibleTurns}
          transportKind={transport.kind}
          lifecycle={lifecycle}
          interview={interview}
          reducedMotion={reducedMotion}
          onRetry={() => runnerRef.current?.retry()}
        />
      )}
      {cards.length > 0 ? (
        <div className="px-3 pb-2 flex flex-col gap-1.5 shrink-0" data-option-cards>
          {cards.map(({ turnId, card, resolved }) => (
            <div key={turnId} className="rounded border border-hairline p-2 flex flex-col gap-1" data-option-card {...(resolved ? { "data-resolved": "" } : {})}>
              <p className="text-xs text-ink dark:text-bright">{card.question}</p>
              <div className="flex flex-wrap gap-1">
                {card.options.map((o) => (
                  <button
                    key={o}
                    type="button"
                    disabled={resolved}
                    onClick={() => send(o)}
                    className="text-xs rounded-full border border-hairline px-2 py-0.5 text-ink dark:text-bright hover:bg-ice-2 dark:hover:bg-charcoal-1 disabled:opacity-60"
                  >
                    {o}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
      ) : null}
      {actions.length > 0 ? (
        <div className="px-3 pb-2 shrink-0">
          <AgentReplyActions tab={tab} actions={actions} interview={interview} onSeedConfirm={(seed) => { dispatchProjectSeed(seed); announce("Project seed handed to the intake"); }} />
        </div>
      ) : null}
      <AgentComposer
        tabId={tab.id}
        draft={draft}
        onDraftChange={setDraft}
        chips={chips}
        onChipsChange={setChips}
        candidates={candidates}
        threadEmpty={turns.length === 0}
        onSend={(text) => send(text)}
        onCannedPrompt={(n) => send(["What should I read next in this project?", "What is missing from this project's evidence?", "Where is this project's argument weakest?"][n - 1])}
        onEscapeRung={onRung}
        hasContextChip={chipVisible}
        recording={recording}
        onStopRecording={() => useAgentPaneStore.getState().setRecording(tab.id, false)}
        active={active && !closing}
        openNonce={openNonce}
        rootRef={rootRef}
        announce={announce}
        disabled={closing}
        reducedMotion={reducedMotion}
      />
    </section>
  );
}

export default AgentPane;
