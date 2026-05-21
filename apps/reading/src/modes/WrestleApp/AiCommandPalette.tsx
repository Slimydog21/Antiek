// SPR-04 M4 — AI command palette overlay.
//
// Distinct from the global navigation CommandPalette
// (src/components/CommandPalette.tsx) — that palette routes between
// surfaces; this one prompts the AI sidecar pipeline.
//
// Wave-2 contract: in WrestleApp, Cmd/Ctrl+K opens THIS overlay (the
// AI palette) instead of the navigation palette. The keydown listener
// in WrestleApp/index.tsx uses `capture: true` so it pre-empts the
// global palette's bubbling-phase listener when WrestleApp is mounted.
//
// Per the sprint spec:
//   - Routes to the existing AI sidecar pipeline (apiFetch /thought-partner).
//     No new AI pipeline is invented; this is just a different surface
//     for the same backend.
//   - Highlighted text (window.getSelection() at the moment of open)
//     is auto-passed as context.
//   - Response renders INSIDE this overlay — never in a side panel.
//     The point of reader mode is calm, so AI output stays modal and
//     dismissable.
//   - Esc closes; focus returns to whatever element WrestleApp passes
//     back via onClose.

import { useCallback, useEffect, useRef, useState } from "react";

import { apiFetch } from "../../lib/api";

interface AiCommandPaletteProps {
  open: boolean;
  onClose: () => void;
  /**
   * Pre-populated context text. WrestleApp captures
   * window.getSelection() at the moment Cmd+K fires and passes the
   * trimmed string here so the overlay opens with the selection as
   * "passed-in context".
   */
  initialContext?: string;
  /**
   * Investigation scope so the AI sidecar can ground its reply. Defaults
   * to the same `__sidecar__` scope the global AISidecar uses when no
   * investigation is active — see src/components/AISidecar.tsx.
   */
  investigationId?: string;
}

interface AiReply {
  shape: "CHALLENGE" | "SYNTHESIS" | "EXTENSION";
  text: string;
}

export default function AiCommandPalette({
  open,
  onClose,
  initialContext,
  investigationId,
}: AiCommandPaletteProps) {
  const [prompt, setPrompt] = useState("");
  const [pending, setPending] = useState(false);
  const [reply, setReply] = useState<AiReply | null>(null);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLTextAreaElement | null>(null);

  // Reset transient UI state every time the overlay opens. Keep the
  // input pre-populated with the prior prompt so re-opening to refine
  // a question is one keystroke away — but clear reply/error so the
  // user is not surprised by stale output.
  useEffect(() => {
    if (open) {
      setReply(null);
      setError(null);
      setTimeout(() => inputRef.current?.focus(), 0);
    }
  }, [open]);

  const submit = useCallback(async () => {
    const text = prompt.trim();
    if (!text || pending) return;
    setPending(true);
    setError(null);
    setReply(null);
    try {
      const composed = initialContext
        ? `Context (highlighted): "${initialContext}"\n\nQuestion: ${text}`
        : text;
      const resp = await apiFetch("/thought-partner", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          investigation_id: investigationId ?? "__sidecar__",
          prompt: composed,
        }),
      });
      if (!resp.ok) {
        setError(`AI unavailable (HTTP ${resp.status}).`);
        return;
      }
      const data = (await resp.json()) as Partial<AiReply> & {
        body?: string;
      };
      setReply({
        shape: data.shape ?? "SYNTHESIS",
        text: data.text ?? data.body ?? JSON.stringify(data),
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setPending(false);
    }
  }, [prompt, pending, initialContext, investigationId]);

  const onKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        void submit();
      } else if (e.key === "Escape") {
        e.preventDefault();
        onClose();
      }
    },
    [submit, onClose],
  );

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[60] bg-stone-900/40 flex items-start justify-center pt-24"
      role="dialog"
      aria-modal="true"
      aria-label="AI command palette"
      data-testid="ai-command-palette"
      onClick={onClose}
    >
      <div
        className="w-[640px] max-w-[90vw] bg-white border border-stone-200 rounded-lg shadow-2xl overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="px-4 py-2 border-b border-stone-200 bg-stone-50 flex items-center justify-between text-[11px] font-mono text-stone-500">
          <span>Ask AI · ⌘K opens · Esc closes · ⌘↵ submit</span>
          {initialContext ? (
            <span
              className="truncate max-w-[40%] text-stone-700"
              title={initialContext}
              data-testid="ai-command-palette-context"
            >
              context: "{initialContext.slice(0, 48)}{initialContext.length > 48 ? "…" : ""}"
            </span>
          ) : null}
        </div>
        <textarea
          ref={inputRef}
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder="Ask the AI sidecar anything…"
          rows={3}
          className="w-full px-4 py-3 text-base font-serif text-stone-900 placeholder:text-stone-400 outline-none resize-y"
          data-testid="ai-command-palette-input"
        />
        <div className="px-4 py-2 border-t border-stone-200 bg-stone-50 flex items-center justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="text-xs px-2.5 py-1 rounded-md border border-stone-300 bg-white text-stone-700 hover:bg-stone-100 transition-colors font-mono"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={() => void submit()}
            disabled={pending || !prompt.trim()}
            className="text-xs px-3 py-1 rounded-md bg-stone-900 text-white hover:bg-stone-700 transition-colors disabled:opacity-50"
            data-testid="ai-command-palette-submit"
          >
            {pending ? "Thinking…" : "Send"}
          </button>
        </div>
        {(reply || error) && (
          <div className="px-4 py-3 border-t border-stone-200">
            {error ? (
              <p
                className="text-xs text-red-700 font-mono"
                data-testid="ai-command-palette-error"
              >
                {error}
              </p>
            ) : reply ? (
              <div
                className="border border-stone-200 rounded p-3 bg-stone-50"
                data-testid="ai-command-palette-reply"
              >
                <p className="text-[10px] font-mono uppercase tracking-wide text-stone-500 mb-1">
                  {reply.shape}
                </p>
                <p className="text-sm text-stone-800 whitespace-pre-wrap font-serif">
                  {reply.text}
                </p>
              </div>
            ) : null}
          </div>
        )}
      </div>
    </div>
  );
}
