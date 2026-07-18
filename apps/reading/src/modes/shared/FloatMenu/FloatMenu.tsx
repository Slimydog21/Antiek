import { useCallback, useEffect, useRef, useState } from "react";

import LemonButton from "../../../components/lemon/LemonButton";
import AIActionFailure from "../../../shared/AIActionFailure";
import { ApiError, editSelection } from "../../../lib/api";
import { useVoiceCapture } from "../../../hooks/useVoiceCapture";
import {
  dialogueOverSelection,
  saveFloatMenuNote,
  searchFloatMenuSelection,
  outboundText,
  WITHHELD_OUTBOUND_REASON,
  type DialogueReply,
  type RewriteActions,
  type SearchResult,
} from "./floatMenuActions";
import type { FloatMenuSelection } from "./useFloatMenuSelection";
// Collective multi-agent float invent — highlight → float windows product door.
import collectiveMergeArt from "../../../brand/werner/poses/session/werner_collective_merge_session_v1.webp";
import "../../../brand/sessionLivingTv.css";
import { emitWernerExperience } from "../../../werner/reactionBus";

/**
 * FloatMenu — THE shared highlight → float-window interaction primitive
 * (Living Roadmap SPR-04). Select text → a float window offering
 * {Note · Dialogue · Search · Deep-research}, by text or voice. Built ONCE
 * here, host-agnostic, and reused (not re-implemented) in Read (SPR-08),
 * Write (SPR-09), and Speak later — they mount THIS component.
 *
 * Generalized from `ResearchWorkstation/HighlightToolbar.tsx` (the shipped
 * single-action "Follow this" toolbar): its selection-listen + positioning
 * moved into {@link useFloatMenuSelection}; its single action became these
 * four. The Research surface still works — HighlightToolbar now renders a
 * FloatMenu (see ResearchWorkstation/index.tsx).
 *
 * ANCHORING (the load-bearing boundary, documented so a maintainer doesn't
 * wrongly couple it to reading-physics): FloatMenu receives a RAW selection
 * rect prop. It does NOT read the DOM and imports NOTHING from
 * `reading-physics/`. A text selection is a TRANSIENT user input, not a
 * semantic persistent anchor, so it is positioned from the raw rect, never the
 * SPR-02 layout-map (which resolves semantic chunk/claim/passage anchors). The
 * HOST owns the pixel read via {@link useFloatMenuSelection}; the menu just
 * positions from the rect it is given (testable with a literal rect).
 *
 * The four actions share ONE selection context — they are deliberately one
 * coherent unit, not four separate buttons (see HYBRID_DECISION.md / the
 * sprint handoff steelman: consistency-across-surfaces + not cluttering
 * Read/Write with four buttons each wins over per-action discoverability).
 */

type FloatMenuView =
  | { kind: "menu" }
  | { kind: "note" }
  | { kind: "dialogue" }
  | { kind: "search" }
  | { kind: "edit" };

export interface FloatMenuProps {
  /** The live selection (text + raw rect + provenance) the host resolved, or
   * null when there is no selection — the menu renders nothing (rigor #3:
   * empty/collapsed selection → no window). */
  selection: FloatMenuSelection | null;
  /** Investigation the surface is scoped to — the typed-event bucket for NOTE
   * + the dialogue session id. */
  investigationId: string;
  /** Deep-research: spawn a child investigation linked to this selection.
   * The host wires this to the REUSED chase path (ChaseThread/ChaseSlideOver +
   * startInvestigation with parent_investigation_id) — FloatMenu does not
   * re-implement child-investigation creation. The host receives the §9.0-safe
   * outbound text (null ⇒ withheld; the host must refuse). */
  onDeepResearch: (safeSpawnText: string | null, selection: FloatMenuSelection) => void;
  /** M4 Hybrid flag (OFF by default). When off, Deep-research launches
   * immediately (= M2). When on, the clarifying-question path is reachable but
   * explicitly marked unfinished. See HYBRID_DECISION.md. */
  hybridEnabled?: boolean;
  /** Write SPR-09 M4: rewrite actions ("rewrite this / make it stronger / spin
   * a sub-agent"). ONLY the Write host passes this; Read/Research/Speak hosts
   * omit it and the menu is byte-for-byte unchanged (D-3 — mode-gated, not a
   * fork). The host owns the SHIPPED generate/spawn paths the intents map to. */
  rewriteActions?: RewriteActions;
  /** CK-5: deliverable/section context a Write host passes so the Edit
   *  panel can call POST /write/edit-selection. Omitted by non-Write hosts. */
  editContext?: { deliverableId: string; sectionId: string };
  /** CK-5: apply the model's edited span. The host splices it into the
   *  section prose (its own selection state identifies the span to replace). */
  onApplyEdit?: (editedText: string) => void;
}

/** Clamp the menu on-screen at a viewport edge (rigor #3). The menu sits above
 * the selection, centered; we clamp left/right so it never spills off the
 * viewport, and flip below when there's no room above. Returns viewport-fixed
 * coords (the menu uses position: fixed, so no scroll offset needed). */
function clampPosition(
  rect: FloatMenuSelection["rect"],
  menuWidth: number,
  menuHeight: number,
  viewportWidth: number,
  viewportHeight: number,
): { top: number; left: number } {
  const margin = 8;
  const centerX = rect.left + rect.width / 2;
  let left = centerX - menuWidth / 2;
  left = Math.max(margin, Math.min(left, viewportWidth - menuWidth - margin));
  // Prefer above the selection; flip below if it would clip the top.
  let top = rect.top - menuHeight - margin;
  if (top < margin) top = rect.top + rect.height + margin;
  top = Math.min(top, viewportHeight - menuHeight - margin);
  top = Math.max(margin, top);
  return { top, left };
}

const MENU_W = 320;
const MENU_H = 44;

/** A small, stable, NON-DISPLAYED hash of a search hit's content for use as a
 * React key on the async, re-orderable results list. djb2 over the displayed
 * fields — deterministic per hit, never rendered, and never a substrate noun
 * (so copy-lint U-04 stays green). Not for identity/security; just a stable
 * key that doesn't reorder under list churn the way an array index would. */
function hashHit(documentTitle: string | null, label: string): string {
  const s = `${documentTitle ?? ""}|${label}`;
  let h = 5381;
  for (let i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) | 0;
  return (h >>> 0).toString(36);
}

export default function FloatMenu({
  selection,
  investigationId,
  onDeepResearch,
  hybridEnabled = false,
  rewriteActions,
  editContext,
  onApplyEdit,
}: FloatMenuProps) {
  const [view, setView] = useState<FloatMenuView>({ kind: "menu" });
  const rootRef = useRef<HTMLDivElement>(null);

  // Reset to the menu whenever a NEW selection arrives (the user re-highlighted
  // somewhere else). A null selection unmounts entirely (handled below).
  const selText = selection?.text ?? null;
  useEffect(() => {
    setView({ kind: "menu" });
  }, [selText]);

  // Dismiss on Esc (rigor #3). Click-away dismissal is the host's concern —
  // a new (empty) selectionchange clears `selection` → unmount; we add an Esc
  // handler that collapses the live selection so the menu closes.
  useEffect(() => {
    if (!selection) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        window.getSelection()?.removeAllRanges();
        setView({ kind: "menu" });
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [selection]);

  // Rigor #3: empty / collapsed / out-of-scope selection → no window. The host
  // hands null in all those cases (useFloatMenuSelection), so this is the one
  // dismissal point.
  if (!selection) return null;

  const pos = clampPosition(
    selection.rect,
    MENU_W,
    MENU_H,
    typeof window !== "undefined" ? window.innerWidth : 1024,
    typeof window !== "undefined" ? window.innerHeight : 768,
  );

  return (
    <div
      ref={rootRef}
      data-floatmenu
      role="menu"
      aria-label="Highlight actions"
      style={{
        position: "fixed",
        top: pos.top,
        left: pos.left,
        zIndex: 50,
        maxWidth: MENU_W,
      }}
      // Don't blur the selection when interacting with the menu — the same
      // guard HighlightToolbar.tsx:82 used so the rect stays valid.
      onMouseDown={(e) => {
        if ((e.target as HTMLElement).tagName !== "TEXTAREA") e.preventDefault();
      }}
      className="bg-ink text-bright rounded-md shadow-lg text-xs font-mono"
    >
      {view.kind === "menu" && (
        <div className="flex flex-col">
          {/* Living-TV invent — float research windows product door. */}
          <img
            src={collectiveMergeArt}
            alt=""
            aria-hidden="true"
            data-testid="float-menu-living-tv-art"
            className="h-8 w-full object-cover object-center rounded-t-md opacity-90 antiek-living-tv-invent"
            loading="lazy"
            decoding="async"
          />
          <div className="flex items-stretch divide-x divide-charcoal-2">
            <MenuButton label="Note" onClick={() => setView({ kind: "note" })} />
            <MenuButton label="Dialogue" onClick={() => setView({ kind: "dialogue" })} />
            <MenuButton label="Search" onClick={() => setView({ kind: "search" })} />
            <MenuButton
              label="Deep-research"
              onClick={() => {
                // DEEP-RESEARCH → the REUSED chase path (host wires
                // ChaseThread + startInvestigation). §9.0: hand the host the
                // guarded outbound text (null ⇒ withheld) so a withheld body
                // never becomes a child investigation's spawn_context.
                const safeText = outboundText(selection);
                // Living-TV: only beat when spawn text is actually launchable.
                if (safeText) emitWernerExperience("deep_research_start");
                onDeepResearch(safeText, selection);
              }}
            />
          </div>
          {/* Write SPR-09 M4: rewrite actions, shown ONLY when the Write host
              supplies them (D-3). Each routes the selection through the §9.0
              chokepoint; the host maps the intent to the SHIPPED generate /
              spawn path. */}
          {rewriteActions && (
            <div
              data-floatmenu-rewrite
              className="flex items-stretch divide-x divide-charcoal-2 border-t border-charcoal-2"
            >
              <MenuButton
                label="Rewrite"
                onClick={() =>
                  rewriteActions.onRewrite({ kind: "rewrite", safeText: outboundText(selection) }, selection)
                }
              />
              <MenuButton
                label="Make stronger"
                onClick={() =>
                  rewriteActions.onRewrite({ kind: "stronger", safeText: outboundText(selection) }, selection)
                }
              />
              <MenuButton
                label="Spin a sub-agent"
                onClick={() =>
                  rewriteActions.onRewrite({ kind: "sub_agent", safeText: outboundText(selection) }, selection)
                }
              />
              {editContext && onApplyEdit && (
                <MenuButton label="Edit…" onClick={() => setView({ kind: "edit" })} />
              )}
            </div>
          )}
        </div>
      )}

      {view.kind === "note" && (
        <NotePanel
          selection={selection}
          investigationId={investigationId}
          onClose={() => setView({ kind: "menu" })}
        />
      )}
      {view.kind === "dialogue" && (
        <DialoguePanel
          selection={selection}
          investigationId={investigationId}
          onClose={() => setView({ kind: "menu" })}
        />
      )}
      {view.kind === "search" && (
        <SearchPanel selection={selection} onClose={() => setView({ kind: "menu" })} />
      )}
      {view.kind === "edit" && editContext && onApplyEdit && (
        <EditPanel
          selection={selection}
          editContext={editContext}
          onApplyEdit={onApplyEdit}
          onClose={() => setView({ kind: "menu" })}
        />
      )}

      {/* M4 Hybrid affordance — flagged, OFF by default. With the flag on, the
          clarifying-question path is REACHABLE but explicitly marked
          unfinished (not a fake that looks done). See HYBRID_DECISION.md. */}
      {hybridEnabled && view.kind === "menu" && (
        <div
          data-floatmenu-hybrid
          className="px-3 py-1.5 border-t border-charcoal-2 text-sun-deep"
          title="Hybrid: the AI may ask clarifying questions before launching. Not yet functional — see HYBRID_DECISION.md."
        >
          Hybrid — coming (AI asks first)
        </div>
      )}
    </div>
  );
}

function MenuButton({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button
      type="button"
      role="menuitem"
      onClick={onClick}
      className="px-3 py-1.5 hover:bg-shadow-2 transition-colors first:rounded-l-md last:rounded-r-md"
    >
      {label}
    </button>
  );
}

// ─── NOTE panel (text + voice) ──────────────────────────────────────────────

function NotePanel({
  selection,
  investigationId,
  onClose,
}: {
  selection: FloatMenuSelection;
  investigationId: string;
  onClose: () => void;
}) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const voice = useVoiceCapture();

  const save = useCallback(
    async (noteText: string) => {
      const t = noteText.trim();
      if (!t) {
        setError("Write or speak a note first.");
        return;
      }
      setBusy(true);
      setError(null);
      try {
        // NOTE → postTypedEvent, source_kind "user" (see floatMenuActions).
        await saveFloatMenuNote({ investigationId, selection, noteText: t });
        setSaved(true);
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setBusy(false);
      }
    },
    [investigationId, selection],
  );

  // Voice: record → transcribe → the USER-sourced transcript becomes the note
  // text. useVoiceCapture pins source_kind "user" + persists voice.captured;
  // the marginalia.noted note is ALSO user-sourced — voice-in is human speech,
  // never relabelled as model output (§9).
  const captureVoice = useCallback(async () => {
    if (voice.phase === "recording") {
      const res = await voice.stopAndCapture({ investigationId });
      if (res) setText((prev) => (prev ? prev + " " : "") + res.transcript);
    } else {
      await voice.start();
    }
  }, [voice, investigationId]);

  if (saved) {
    return (
      <Panel title="Noted" onClose={onClose}>
        <p className="text-aurora">Saved — user-sourced, anchored to your selection.</p>
      </Panel>
    );
  }

  return (
    <Panel title="Note" onClose={onClose}>
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="Type a note, or speak it…"
        rows={3}
        className="w-full bg-shadow-2 text-bright rounded p-1.5 resize-none outline-none"
        autoFocus
      />
      {/* Mic-permission-denied surfaces honestly (rigor #3), never a crash.
          useVoiceCapture.start() does NOT re-throw a denial — it reflects in
          recorderState "denied" — so we read that AND voice.error (ASR/503). */}
      {voice.recorderState === "denied" && (
        <p className="text-sun-deep mt-1" role="alert">
          Microphone permission was denied. You can still type a note.
        </p>
      )}
      {voice.error && (
        <p className="text-emperor mt-1" role="alert">
          {voice.error}
        </p>
      )}
      {error && (
        <p className="text-emperor mt-1" role="alert">
          {error}
        </p>
      )}
      <div className="flex items-center gap-2 mt-2">
        <LemonButton variant="primary" size="sm" disabled={busy} onClick={() => void save(text)}>
          {busy ? "Saving…" : "Save note"}
        </LemonButton>
        <LemonButton
          variant="tertiary"
          size="sm"
          onClick={() => void captureVoice()}
          disabled={voice.phase === "transcribing" || voice.phase === "persisting"}
        >
          {voice.phase === "recording"
            ? "■ Stop"
            : voice.phase === "transcribing"
              ? "Listening…"
              : "● Speak it"}
        </LemonButton>
      </div>
    </Panel>
  );
}

// ─── DIALOGUE panel (text + voice) ──────────────────────────────────────────

function DialoguePanel({
  selection,
  investigationId,
  onClose,
}: {
  selection: FloatMenuSelection;
  investigationId: string;
  onClose: () => void;
}) {
  const [followUp, setFollowUp] = useState("");
  const [pending, setPending] = useState(false);
  const [reply, setReply] = useState<DialogueReply | null>(null);
  const [failure, setFailure] = useState<{ reason: string | null } | null>(null);
  const voice = useVoiceCapture();

  const send = useCallback(
    async (extra: string) => {
      setPending(true);
      setReply(null);
      setFailure(null);
      try {
        // DIALOGUE → /thought-partner (the reply is MODEL-sourced; the prompt
        // incl. any voice transcript is USER-sourced — kept distinct).
        const r = await dialogueOverSelection({
          investigationId,
          selection,
          followUp: extra,
        });
        setReply(r);
      } catch (e) {
        // No-key 503 → null reason → AIActionFailure's "provider isn't
        // configured" sentence (VoiceChaseButton.tsx:56 pattern). Honest, not
        // a fabricated reply.
        const status = e instanceof ApiError ? e.status : 0;
        setFailure({ reason: status === 503 ? null : e instanceof Error ? e.message : String(e) });
      } finally {
        setPending(false);
      }
    },
    [investigationId, selection],
  );

  // Voice feeds the user prompt (speak the follow-up instead of typing).
  const captureVoice = useCallback(async () => {
    if (voice.phase === "recording") {
      const res = await voice.stopAndCapture({ investigationId });
      if (res) setFollowUp((prev) => (prev ? prev + " " : "") + res.transcript);
    } else {
      await voice.start();
    }
  }, [voice, investigationId]);

  if (failure) {
    return (
      <Panel title="Dialogue" onClose={onClose}>
        <AIActionFailure
          title="Couldn’t get a reply"
          reason={failure.reason}
          onRetry={() => setFailure(null)}
          retryLabel="Try again"
        />
      </Panel>
    );
  }

  return (
    <Panel title="Dialogue" onClose={onClose}>
      {/* The user's quoted selection — visibly USER-sourced. */}
      <blockquote className="text-moonlight italic border-l-edge border-sun pl-2 mb-1.5 line-clamp-3">
        "{selection.text}"
      </blockquote>
      {reply && (
        // The MODEL reply — labelled, never conflated with the user's words.
        <div className="bg-shadow-2 rounded p-1.5 mb-1.5">
          <span className="text-[10px] uppercase tracking-wider text-moonlight block mb-0.5">
            AI reply
          </span>
          <p className="text-bright whitespace-pre-wrap leading-relaxed">{reply.reply}</p>
        </div>
      )}
      <textarea
        value={followUp}
        onChange={(e) => setFollowUp(e.target.value)}
        placeholder="Ask about this passage (one-shot)…"
        rows={2}
        className="w-full bg-shadow-2 text-bright rounded p-1.5 resize-none outline-none"
        autoFocus
      />
      {voice.recorderState === "denied" && (
        <p className="text-sun-deep mt-1" role="alert">
          Microphone permission was denied. You can still type your question.
        </p>
      )}
      {voice.error && (
        <p className="text-emperor mt-1" role="alert">
          {voice.error}
        </p>
      )}
      <div className="flex items-center gap-2 mt-2">
        <LemonButton variant="primary" size="sm" disabled={pending} onClick={() => void send(followUp)}>
          {pending ? "Asking…" : reply ? "Ask again" : "Ask"}
        </LemonButton>
        <LemonButton
          variant="tertiary"
          size="sm"
          onClick={() => void captureVoice()}
          disabled={voice.phase === "transcribing" || voice.phase === "persisting"}
        >
          {voice.phase === "recording" ? "■ Stop" : "● Speak it"}
        </LemonButton>
      </div>
      <p className="text-[10px] text-moonlight mt-1.5">One-shot reply (not a full chat) this sprint.</p>
    </Panel>
  );
}

// ─── SEARCH panel ────────────────────────────────────────────────────────────

function SearchPanel({
  selection,
  onClose,
}: {
  selection: FloatMenuSelection;
  onClose: () => void;
}) {
  const [pending, setPending] = useState(true);
  const [result, setResult] = useState<SearchResult | null>(null);
  const [withheld, setWithheld] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setPending(true);
    setError(null);
    void (async () => {
      try {
        // SEARCH → searchBlocks (corpus). §9.0: a withheld selection returns
        // null here (no body leaves the client) → show the withheld reason.
        const r = await searchFloatMenuSelection(selection);
        if (cancelled) return;
        if (r === null) setWithheld(true);
        else setResult(r);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      } finally {
        if (!cancelled) setPending(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [selection]);

  return (
    <Panel title="Search the corpus" onClose={onClose}>
      {withheld ? (
        <p className="text-sun-deep" role="alert">
          {WITHHELD_OUTBOUND_REASON}
        </p>
      ) : pending ? (
        <p className="text-moonlight">Searching…</p>
      ) : error ? (
        <p className="text-emperor" role="alert">
          {error}
        </p>
      ) : result && result.count > 0 ? (
        <ul className="flex flex-col gap-1 max-h-48 overflow-y-auto">
          {result.hits.map((h, i) => (
            // Stable, content-derived React key for this async, re-orderable
            // list — NOT the array index (a React smell on re-orderable data),
            // and NOT a user-facing substrate noun (copy-lint U-04: the internal
            // handle is never written here). It hashes the hit's displayed
            // fields; the trailing `i` only disambiguates exact-duplicate hits.
            <li key={`${hashHit(h.document_title, h.label)}-${i}`} className="text-bright">
              <span className="text-moonlight">{h.document_title ?? "—"}</span> · {h.label}
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-moonlight">No matches in the corpus.</p>
      )}
    </Panel>
  );
}

// ─── shared panel chrome ──────────────────────────────────────────────────────

function Panel({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
}) {
  return (
    <div className="p-2 w-[300px]">
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-[10px] uppercase tracking-wider text-moonlight">{title}</span>
        <button
          type="button"
          onClick={onClose}
          className="text-moonlight hover:text-bright"
          aria-label="Back to menu"
        >
          ←
        </button>
      </div>
      {children}
    </div>
  );
}

// ─── EDIT panel (CK-5 — Cmd+K selection edit) ──────────────────────────────

function EditPanel({
  selection,
  editContext,
  onApplyEdit,
  onClose,
}: {
  selection: FloatMenuSelection;
  editContext: { deliverableId: string; sectionId: string };
  onApplyEdit: (editedText: string) => void;
  onClose: () => void;
}) {
  const [instruction, setInstruction] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const safeText = outboundText(selection);

  async function runEdit() {
    if (safeText === null) {
      setError(WITHHELD_OUTBOUND_REASON);
      return;
    }
    if (instruction.trim().length === 0) return;
    setBusy(true);
    setError(null);
    try {
      const res = await editSelection({
        deliverable_id: editContext.deliverableId,
        section_id: editContext.sectionId,
        selection_text: safeText,
        instruction: instruction.trim(),
      });
      onApplyEdit(res.edited_text);
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "edit failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Panel title="Edit selection" onClose={onClose}>
      <div data-floatmenu-edit className="flex flex-col gap-1.5">
        {safeText === null ? (
          <p className="text-sun-deep" role="alert">
            {WITHHELD_OUTBOUND_REASON}
          </p>
        ) : null}
        {error ? (
          <p className="text-emperor" role="alert">
            {error}
          </p>
        ) : null}
        <textarea
          value={instruction}
          onChange={(e) => setInstruction(e.target.value)}
          placeholder="e.g. make it more concise"
          rows={2}
          className="w-full rounded border border-charcoal-2 bg-shadow-2 p-1.5 text-bright"
          disabled={busy}
        />
        <div className="flex gap-1.5">
          <LemonButton
            variant="primary"
            size="sm"
            disabled={busy || safeText === null || instruction.trim().length === 0}
            onClick={() => void runEdit()}
          >
            {busy ? "Editing…" : "Edit"}
          </LemonButton>
        </div>
      </div>
    </Panel>
  );
}

