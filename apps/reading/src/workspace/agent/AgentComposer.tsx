/**
 * AgentComposer.tsx — the pane's composer (SPR-07 M2).
 *
 * ALL key handling is on the element's onKeyDown, never a window/document
 * keydown (windowKeyListenerCensus.test.ts). Every handled key is
 * preventDefault + stopPropagation, so PanelLayout's fullscreen Escape
 * owner (which skips defaultPrevented and text targets) never double-fires.
 *
 * Key contract: composerKeys.resolveComposerKey (Enter sends, Shift+Enter
 * newline, IME-safe). Escape ladder: picker → recording → chip → blur
 * (focus to the pane root) — "close" is the ROOT's own key (AgentPane).
 * Digits 1/2/3 pick a canned prompt only with an empty thread and an
 * untouched empty draft (fix 6). @agent / #source chips with a combobox +
 * listbox picker (fix 7). Paste-anywhere (pattern 12): ONE document paste
 * listener while this composer belongs to the active tab, firing only when
 * no editable element has focus, no modal is open, and the pane is visible.
 */
import { useEffect, useId, useLayoutEffect, useMemo, useRef, useState, type RefObject } from "react";

import { topModal } from "../escapeOverlay";
import { isTextEditing } from "../shortcuts";
import { backspaceRemovesLastChip, type ChipCandidate, type ComposerChip } from "./composerChips";
import { cannedPromptForDigit, nextEscapeRung, resolveComposerKey, type EscapeRung } from "./composerKeys";

export interface AgentComposerProps {
  tabId: string;
  draft: string;
  onDraftChange: (value: string) => void;
  chips: readonly ComposerChip[];
  onChipsChange: (chips: ComposerChip[]) => void;
  candidates: { agents: readonly ChipCandidate[]; sources: readonly ChipCandidate[] };
  threadEmpty: boolean;
  onSend: (text: string) => void;
  onCannedPrompt: (index: 1 | 2 | 3) => void;
  /** Every rung the composer walks (picker, recording, chip, blur); the
   *  pane acts on chip and blur. */
  onEscapeRung: (rung: EscapeRung) => void;
  hasContextChip: boolean;
  recording: boolean;
  onStopRecording: () => void;
  /** Paste-anywhere is installed only for the ACTIVE tab's composer. */
  active: boolean;
  /** Bumped by openAgentPane on re-activation: refocus without a frame wait. */
  openNonce: number;
  rootRef: RefObject<HTMLElement | null>;
  announce: (text: string) => void;
  disabled?: boolean;
  reducedMotion?: boolean;
}

const TOKEN = /(^|\s)([@#])(\S*)$/;
const GROW_MS = 120;

export function AgentComposer(p: AgentComposerProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const draftRef = useRef(p.draft);
  draftRef.current = p.draft;
  const [touched, setTouched] = useState(false);
  const [dismissedFor, setDismissedFor] = useState<string | null>(null);
  const [highlighted, setHighlighted] = useState(0);
  const caretToEnd = useRef(false);
  const id = useId();
  const listboxId = `${id}-listbox`;

  const token = useMemo(() => {
    const m = TOKEN.exec(p.draft);
    return m ? { sigil: m[2] as "@" | "#", query: m[3], start: m.index + m[1].length } : null;
  }, [p.draft]);
  const options = useMemo(() => {
    if (!token) return [];
    const pool = token.sigil === "@" ? p.candidates.agents : p.candidates.sources;
    const q = token.query.toLowerCase();
    return pool.filter((c) => c.label.toLowerCase().includes(q));
  }, [token, p.candidates]);
  const pickerOpen = token !== null && options.length > 0 && dismissedFor !== p.draft;
  const highlight = pickerOpen ? Math.min(highlighted, options.length - 1) : -1;
  const optionId = (i: number) => `${id}-opt-${i}`;

  // Focus on mount and on re-activation: synchronously after commit, never "next frame" (fix 4).
  useEffect(() => {
    textareaRef.current?.focus();
  }, [p.tabId, p.openNonce]);

  useLayoutEffect(() => {
    if (!caretToEnd.current) return;
    caretToEnd.current = false;
    const ta = textareaRef.current;
    if (ta) ta.setSelectionRange(ta.value.length, ta.value.length);
  }, [p.draft]);

  // Grows from the bottom edge (pattern 14): WAAPI 120 ms, snap under reduced motion.
  const lastHeight = useRef<number | null>(null);
  useLayoutEffect(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    const next = ta.scrollHeight;
    if (!next) return;
    ta.style.height = `${next}px`;
    const prev = lastHeight.current;
    lastHeight.current = next;
    if (prev !== null && prev !== next && !p.reducedMotion && typeof ta.animate === "function") {
      ta.animate([{ height: `${prev}px` }, { height: `${next}px` }], { duration: GROW_MS, easing: "cubic-bezier(0.2,0,0,1)" });
    }
  }, [p.draft, p.reducedMotion]);

  // Paste-anywhere (fix 2).
  const { active, rootRef, onDraftChange } = p;
  useEffect(() => {
    if (!active) return;
    const onPaste = (e: ClipboardEvent) => {
      const root = rootRef.current;
      const ta = textareaRef.current;
      if (!root || !ta) return;
      const focused = document.activeElement;
      if (focused && focused !== document.body && isTextEditing(focused)) return;
      if (topModal()) return;
      if (root.hasAttribute("inert") || root.closest("[hidden]") || root.getClientRects().length === 0) return;
      const text = e.clipboardData?.getData("text/plain");
      if (!text) return;
      e.preventDefault();
      caretToEnd.current = true;
      setTouched(true);
      onDraftChange(draftRef.current + text);
      ta.focus();
    };
    document.addEventListener("paste", onPaste);
    return () => document.removeEventListener("paste", onPaste);
  }, [active, rootRef, onDraftChange]);

  const consume = (e: React.KeyboardEvent) => {
    e.preventDefault();
    e.stopPropagation();
  };

  const complete = (i: number) => {
    const pick = options[i];
    if (!pick || !token) return;
    p.onChipsChange([...p.chips, { kind: token.sigil === "@" ? "agent" : "source", id: pick.id, label: pick.label }]);
    p.onDraftChange(p.draft.slice(0, token.start));
    setHighlighted(0);
  };

  const removeChip = (chip: ComposerChip) => {
    p.onChipsChange(p.chips.filter((c) => c !== chip));
    p.announce("Context removed");
    textareaRef.current?.focus();
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Escape") {
      const rung = nextEscapeRung({ pickerOpen, recording: p.recording, hasChip: p.hasContextChip, composerFocused: true });
      consume(e);
      if (rung === "picker") setDismissedFor(p.draft);
      else if (rung === "recording") p.onStopRecording();
      else if (rung === "blur") rootRef.current?.focus();
      p.onEscapeRung(rung);
      return;
    }
    if (!e.ctrlKey && !e.metaKey && !e.altKey) {
      const canned = cannedPromptForDigit(e.key, { threadEmpty: p.threadEmpty, draftEmpty: p.draft === "", modified: touched });
      if (canned !== null) {
        consume(e);
        p.onCannedPrompt(canned);
        return;
      }
    }
    if (e.key === "Backspace" && !e.ctrlKey && !e.metaKey && !e.altKey) {
      const r = backspaceRemovesLastChip(p.chips, p.draft);
      if (r.removed) {
        consume(e);
        p.onChipsChange(r.chips);
        p.announce("Context removed");
        return;
      }
    }
    const r = resolveComposerKey({
      key: e.key, shift: e.shiftKey, isComposing: e.nativeEvent.isComposing, pickerOpen, optionCount: options.length, highlighted: highlight,
    });
    switch (r.action) {
      case "send":
        consume(e);
        if (p.disabled) return;
        if (p.draft.trim() || p.chips.length) p.onSend(p.draft);
        return;
      case "complete":
        consume(e);
        complete(highlight);
        return;
      case "dismiss":
        consume(e);
        setDismissedFor(p.draft);
        return;
      case "move-up":
      case "move-down":
        consume(e);
        setHighlighted(r.highlighted ?? 0);
        return;
      case "newline":
      case "none":
        return;
    }
  };

  return (
    <div className="shrink-0 border-t border-hairline p-2 flex flex-col gap-1" data-agent-composer>
      {p.chips.length > 0 ? (
        <div className="flex flex-wrap gap-1">
          {p.chips.map((chip) => (
            <span
              key={`${chip.kind}:${chip.id}`}
              data-agent-chip={chip.id}
              className="inline-flex items-center gap-1 rounded-full border border-hairline bg-ice-1 dark:bg-charcoal-1 px-2 text-xxs font-mono text-ink dark:text-bright"
            >
              {chip.kind === "agent" ? "@" : "#"}{chip.label}
              <button type="button" aria-label={`Remove ${chip.label}`} className="text-shadow-1 hover:text-bright" onClick={() => removeChip(chip)}>
                ×
              </button>
            </span>
          ))}
        </div>
      ) : null}
      {p.recording ? (
        <p className="text-xxs font-mono text-emperor" data-agent-recording>Recording… (stub; Esc stops)</p>
      ) : null}
      <div className="relative">
        <textarea
          ref={textareaRef}
          value={p.draft}
          disabled={p.disabled}
          rows={2}
          onChange={(e) => { setTouched(true); p.onDraftChange(e.target.value); }}
          onKeyDown={onKeyDown}
          placeholder="Ask about this project… (@ an agent, # a source)"
          aria-label="Ask the agent"
          role="combobox"
          aria-expanded={pickerOpen}
          aria-autocomplete="list"
          aria-haspopup="listbox"
          {...(pickerOpen ? { "aria-controls": listboxId, "aria-activedescendant": optionId(highlight) } : {})}
          className="w-full bg-shadow-2 text-bright rounded p-1.5 text-sm resize-none outline-none focus-visible:ring-2 focus-visible:ring-sun min-h-[2.5rem]"
        />
        {pickerOpen ? (
          <ul
            id={listboxId}
            role="listbox"
            aria-label={token?.sigil === "@" ? "Agents" : "Sources"}
            className="absolute bottom-full left-0 mb-1 z-10 w-full max-h-40 overflow-y-auto rounded border border-hairline bg-ice-0 dark:bg-charcoal-2 shadow-z2 py-1"
          >
            {options.map((o, i) => (
              <li
                key={o.id}
                id={optionId(i)}
                role="option"
                aria-selected={i === highlight}
                onMouseDown={(e) => { e.preventDefault(); complete(i); }}
                className={`px-2 py-1 text-xs text-ink dark:text-bright cursor-default ${i === highlight ? "bg-ice-2 dark:bg-charcoal-1" : ""}`}
              >
                {o.label}
              </li>
            ))}
          </ul>
        ) : null}
      </div>
      <p className="text-xxs text-shadow-1 dark:text-moonlight">Enter sends · Shift+Enter newline · Esc steps back</p>
    </div>
  );
}
