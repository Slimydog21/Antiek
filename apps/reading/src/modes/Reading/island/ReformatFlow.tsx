/**
 * ReformatFlow — the reformat prompt on the island's expanded card
 * (reformat-provenance SPR-02). The operator's "the subagent on the right
 * where I prompted stays as an agent engagement": the prompt launches a
 * GENERATION thread through the EXISTING spawn machinery (runSpawnFlow's
 * pin→spin→link discipline — the island's anchor is already pinned, so the
 * pin step returns it without re-pinning; the spin is the reformat POST;
 * the link 409-keeps honestly — the island's thread holds the anchor).
 *
 * ASK-TO-OPEN: when the generation completes, the card ASKS to open the
 * derived document — the operator confirms (never auto-opened) and the
 * derived document opens BESIDE the source as the ONE reader window for
 * its id, with the reformat origin (the generation thread). Declining
 * opens nothing — the derived document stays registered (honest: it's in
 * the library whenever the operator wants it).
 */
import { useState } from "react";

import { linkAnchorInvestigation } from "../../../lib/api";
import type { BookAnchor } from "../../../lib/api";
import { openWindow, readerWindowId } from "../../../components/windows/openWindow";
import { toast } from "../../../components/lemon/LemonToast";
import LemonButton from "../../../components/lemon/LemonButton";
import LemonTextarea from "../../../components/lemon/LemonTextarea";
import { postReformat } from "../../../api/reformat";
import type { ReformatMode, ReformatResponse } from "../../../api/reformat";
import { runSpawnFlow } from "./spawnFlows";

export interface ReformatFlowProps {
  documentId: string;
  /** The island's anchor — ALREADY pinned by construction; the flow's pin
   *  step returns it, never re-pins. */
  anchorId: string;
  /** The island's passage quote (the operator's reading context) — null on
   *  a metadata-only anchor. */
  passageQuote: string | null;
  onClose: () => void;
}

type Phase = "composing" | "busy" | "ask" | "done" | "error";

export default function ReformatFlow({
  documentId,
  anchorId,
  passageQuote,
  onClose,
}: ReformatFlowProps) {
  const [phase, setPhase] = useState<Phase>("composing");
  const [prompt, setPrompt] = useState("");
  const [mode, setMode] = useState<ReformatMode>("time_window");
  const [result, setResult] = useState<ReformatResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function launch() {
    const q = prompt.trim();
    if (q.length < 3) {
      setError("Say what you want the reformat to do first.");
      return;
    }
    setPhase("busy");
    setError(null);
    let captured: ReformatResponse | null = null;
    const flow = await runSpawnFlow({
      anchors: [],
      locate: () => null,
      // The island's anchor EXISTS (the island is its surface) — the pin
      // step returns it; no POST, no duplicate.
      pin: async () => ({ anchor_id: anchorId }) as BookAnchor,
      spin: async () => {
        const r = await postReformat(documentId, { prompt: q, mode });
        captured = r;
        return { investigation_id: r.thread_id };
      },
      link: (aid, iid) => linkAnchorInvestigation(documentId, aid, iid),
      passageText: passageQuote ?? "",
    });
    if (flow.ok && captured) {
      setResult(captured);
      setPhase("ask");
    } else {
      setError(flow.message ?? "The reformat didn't start.");
      setPhase("error");
      if (!flow.ok) toast.warn(flow.message ?? "The reformat didn't start.");
    }
  }

  function openDerived() {
    if (!result) return;
    openWindow(
      "reader",
      {
        documentId: result.derived_document_id,
        origin: { from: "reformat", id: result.thread_id },
      },
      { id: readerWindowId(result.derived_document_id), title: "Reformatted source" },
    );
    setPhase("done");
  }

  if (phase === "ask" && result) {
    return (
      <div data-reformat-ask className="mb-2 border-t border-hairline pt-2">
        <p className="text-shadow-1 dark:text-moonlight mb-1.5" role="status">
          Your reformatted version is ready — open it beside this book?
        </p>
        <div className="flex items-center gap-2">
          <LemonButton variant="primary" size="sm" onClick={openDerived}>
            Open it
          </LemonButton>
          <button
            type="button"
            onClick={() => setPhase("done")}
            className="text-shadow-1 hover:text-ink dark:hover:text-bright"
            title="The derived document stays in your library whenever you want it"
          >
            Not now
          </button>
        </div>
      </div>
    );
  }

  if (phase === "done") {
    return (
      <div data-reformat-done className="mb-2 border-t border-hairline pt-2">
        <p className="text-shadow-1 dark:text-moonlight mb-1.5" role="status">
          {result ? "Reformatted — it's yours in the library whenever you want it." : "Closed."}
        </p>
        <button
          type="button"
          onClick={onClose}
          className="text-shadow-1 hover:text-ink dark:hover:text-bright"
        >
          Done
        </button>
      </div>
    );
  }

  return (
    <div data-reformat-flow className="mb-2 border-t border-hairline pt-2">
      <label className="text-xxs font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight block mb-1">
        Reformat this book
      </label>
      <div className="mb-1.5 flex items-center gap-2 text-xxs font-mono text-shadow-1 dark:text-moonlight">
        <button
          type="button"
          onClick={() => setMode("time_window")}
          aria-pressed={mode === "time_window"}
          className={mode === "time_window" ? "text-sun-deep dark:text-sun underline" : ""}
        >
          read in a time window
        </button>
        <button
          type="button"
          onClick={() => setMode("themes")}
          aria-pressed={mode === "themes"}
          className={mode === "themes" ? "text-sun-deep dark:text-sun underline" : ""}
        >
          around themes &amp; questions
        </button>
      </div>
      <LemonTextarea
        value={prompt}
        onChange={(e) => setPrompt(e.target.value)}
        disabled={phase === "busy"}
        minRows={2}
        maxRows={6}
        aria-label="What should the reformat do?"
      />
      {error && (
        <p className="mt-1 text-xxs font-mono text-emperor" role="alert">
          {error}
        </p>
      )}
      <div className="flex items-center justify-end gap-2 mt-2">
        <button
          type="button"
          onClick={onClose}
          className="text-shadow-1 hover:text-ink dark:hover:text-bright"
        >
          Cancel
        </button>
        <LemonButton
          variant="primary"
          size="sm"
          onClick={() => void launch()}
          disabled={phase === "busy" || prompt.trim().length < 3}
        >
          {phase === "busy" ? "Reformatting…" : "Reformat"}
        </LemonButton>
      </div>
    </div>
  );
}
