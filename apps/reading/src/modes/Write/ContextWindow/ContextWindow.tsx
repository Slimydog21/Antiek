import { useState } from "react";

import type { PaletteDragPayload } from "../../CreationStudio/BlockPalette";
import { parsePaletteDrag } from "../Repository/dragToOutline";
import { emitWernerExperience } from "../../../werner/reactionBus";
import { generateSection, promoteContext, type GenerationResult } from "../writeApi";
import {
  contextToPromoteRequest,
  generatability,
  type ContextItem,
  type ContextWindowState,
} from "./contextWindowState";

/**
 * Pre-outline context window (specs/write/ SPR-08).
 *
 * The outline-optional path: drop lego blocks (from the Repository — same
 * DRAG_MIME), state an objective by text (voice reuses the existing
 * VoiceNoteCapture; wired where mounted), then generate directly. "Generate"
 * promotes the loose context to a structured outline (provenance preserved)
 * and generates its section — reusing SPR-06's citation + gate + gap
 * contract, not a parallel generator. The window can also just be promoted
 * (kept loose → structured) without generating.
 *
 * The no-blocks-no-fabrication gate is enforced by ``generatability`` (the
 * pure core, tested): an objective with no blocks prompts for blocks rather
 * than inventing sources.
 */
export interface ContextWindowProps {
  className?: string;
}

export function ContextWindow({ className }: ContextWindowProps) {
  const [state, setState] = useState<ContextWindowState>({
    title: "", objective: "", items: [],
  });
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<GenerationResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const gate = generatability(state);

  function addItem(item: ContextItem) {
    setState((s) => ({ ...s, items: [...s.items, item] }));
  }
  function removeItem(index: number) {
    setState((s) => ({ ...s, items: s.items.filter((_, i) => i !== index) }));
  }

  function onDrop(e: React.DragEvent) {
    const payload: PaletteDragPayload | null = parsePaletteDrag(e.dataTransfer);
    if (!payload) return;
    e.preventDefault();
    addItem({ label: payload.label, block_kind: "insight", node_id: payload.block_id });
  }

  async function onGenerate() {
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const promoted = await promoteContext(contextToPromoteRequest(state));
      const gen = await generateSection(promoted.section_id);
      setResult(gen);
      // Living-TV: outline-optional generate completed — happy craft.
      emitWernerExperience("piece_started");
    } catch (e) {
      setError(String(e));
      emitWernerExperience("fail");
    } finally {
      setBusy(false);
    }
  }

  async function onPromoteOnly() {
    setBusy(true);
    setError(null);
    try {
      await promoteContext(contextToPromoteRequest(state));
      // Living-TV: context promoted to structured outline — noted.
      emitWernerExperience("note_saved");
    } catch (e) {
      setError(String(e));
      emitWernerExperience("fail");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={"flex flex-col gap-3 p-4 " + (className ?? "")} data-mode="write-context-window">
      <input
        type="text"
        value={state.title}
        onChange={(e) => setState((s) => ({ ...s, title: e.target.value }))}
        placeholder="Title (optional — defaults to your objective)"
        className="px-3 py-1.5 border border-rule dark:border-charcoal-1 rounded focus:outline-none focus:ring-2 focus:ring-sun"
      />

      {/* Drop zone for repository blocks. */}
      <div
        onDragOver={(e) => {
          if (e.dataTransfer.types.includes("application/x-antiek-block")) {
            e.preventDefault();
            e.dataTransfer.dropEffect = "copy";
          }
        }}
        onDrop={onDrop}
        className="min-h-[96px] border-2 border-dashed border-rule dark:border-charcoal-1 rounded p-3 flex flex-wrap gap-2 content-start"
      >
        {state.items.length === 0 && (
          <p className="text-xs text-ink-mute italic">
            Drag lego blocks here from the repository — no outline needed.
          </p>
        )}
        {state.items.map((item, i) => (
          <span
            key={`${item.node_id ?? item.content}-${i}`}
            className="inline-flex items-center gap-1.5 px-2 py-1 rounded bg-ocean/10 text-ocean text-xs font-serif"
          >
            {item.label}
            <button
              type="button"
              onClick={() => removeItem(i)}
              aria-label="Remove block"
              className="text-ink-mute hover:text-emperor leading-none"
            >
              ✕
            </button>
          </span>
        ))}
      </div>

      <textarea
        value={state.objective}
        onChange={(e) => setState((s) => ({ ...s, objective: e.target.value }))}
        rows={2}
        placeholder="State the writing objective (text or voice)…"
        className="px-3 py-2 border border-rule dark:border-charcoal-1 rounded font-serif focus:outline-none focus:ring-2 focus:ring-sun"
      />

      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={onGenerate}
          disabled={busy || !gate.ok}
          title={gate.ok ? "Generate a cited draft" : gate.reason}
          className="px-3 py-1.5 bg-ink hover:bg-shadow-2 disabled:bg-glacial-1 text-white text-sm rounded"
        >
          {busy ? "Generating…" : "Generate draft"}
        </button>
        <button
          type="button"
          onClick={onPromoteOnly}
          disabled={busy || state.items.length === 0}
          className="px-3 py-1.5 text-sm text-ink-soft hover:text-ink underline"
        >
          Promote to outline
        </button>
        {!gate.ok && <span className="text-xs text-ink-mute">{gate.reason}</span>}
      </div>

      {error && <p className="text-xs text-emperor">{error}</p>}
      {result && (
        <div className="border border-rule dark:border-charcoal-1 rounded p-3">
          {result.status === "gap" && (
            <p className="text-xs text-ink-mute italic">{result.detail}</p>
          )}
          {result.status === "gate_failed" && (
            <p className="text-xs text-emperor">Voice/style gate not met — {result.detail}</p>
          )}
          {result.status === "generated" && (
            <>
              <p className="font-serif text-sm text-ink dark:text-bright whitespace-pre-line">
                {result.prose_text}
              </p>
              {result.unsupported_paragraphs && result.unsupported_paragraphs.length > 0 && (
                <p className="mt-2 text-[11px] text-shadow-1">
                  {result.unsupported_paragraphs.length} paragraph(s) flagged unsupported —
                  verify before keeping.
                </p>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}

export default ContextWindow;
