/**
 * FlagForDiligence — the one calm "flag for diligence" action shared by
 * every flag surface (autonomous-diligence SPR-01): the DRW Canvas block,
 * the unit-2 island outcome card, DistillView's rows, and the artifact
 * receipt window's open questions.
 *
 * One click opens the tiny composer; the note is OPTIONAL (capped, never
 * required) — Enter or "Flag" submits, Esc/Cancel closes. The POST carries
 * REFS ONLY: the node's id, its kind, the source investigation/document
 * ids, and the note — never the node's text (the withheld-text door: a
 * withheld-source flag is lawful exactly because nothing but the ref ever
 * leaves the client). Re-flagging is safe (the server is idempotent), and
 * a successful flag pings the queue rail via notifyDiligenceChanged.
 */
import { useEffect, useRef, useState } from "react";

import type { DistilledNode } from "../lib/api";
import { ApiError } from "../lib/api";
import { createFlag, notifyDiligenceChanged } from "../api/diligence";
import { NOTE_MAX_CHARS } from "./flagCopy";
import { ESC_OVERLAY_PROPS, topModal } from "../workspace/escapeOverlay";

export interface FlagForDiligenceProps {
  /** The distilled node being flagged (its id + kind + source — its text
   *  NEVER crosses into the request). */
  node: DistilledNode;
  /** The investigation the node was distilled from. */
  sourceInvestigationId: string;
}

type Phase = "idle" | "composing" | "busy" | "flagged" | "error";

export default function FlagForDiligence({ node, sourceInvestigationId }: FlagForDiligenceProps) {
  const [phase, setPhase] = useState<Phase>("idle");
  const [note, setNote] = useState("");
  const [reason, setReason] = useState<string | null>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const returnFocus = useRef(false);
  function closeComposer() {
    if (phase === "busy") return;
    returnFocus.current = true;
    setPhase("idle");
  }
  useEffect(() => {
    if (phase !== "idle" || !returnFocus.current) return;
    returnFocus.current = false;
    const trigger = triggerRef.current;
    if (trigger?.isConnected && !trigger.closest('[hidden], [aria-hidden="true"], [inert]')) {
      trigger.focus({ preventScroll: true });
    }
  }, [phase]);


  async function flag() {
    setPhase("busy");
    setReason(null);
    try {
      await createFlag({
        kind: node.kind === "insight" ? "insight" : "open_question",
        object_ref: node.node_id,
        note: note.trim() || null,
        source_investigation_id: sourceInvestigationId,
        source_document_id: node.source_document_id ?? null,
      });
      setPhase("flagged");
      notifyDiligenceChanged();
    } catch (e) {
      setReason(e instanceof ApiError ? e.body || null : null);
      setPhase("error");
    }
  }

  if (phase === "flagged") {
    return (
      <span className="font-mono text-success" role="status" data-diligence-flagged>
        flagged — in your diligence queue
      </span>
    );
  }

  if (phase === "composing" || phase === "busy" || phase === "error") {
    return (
      <span
        {...ESC_OVERLAY_PROPS}
        className="inline-flex items-center gap-1.5"
        data-diligence-composer
        onKeyDown={(event) => {
          if (event.key !== "Escape" || event.defaultPrevented || event.nativeEvent.isComposing ||
              event.ctrlKey || event.metaKey || event.altKey || event.shiftKey || event.getModifierState("AltGraph") ||
              event.currentTarget.closest('[hidden], [aria-hidden="true"], [inert]') || topModal()) return;
          const target = event.target;
          if (!(target instanceof Element) || target.closest("[data-esc-overlay]") !== event.currentTarget) return;
          event.preventDefault();
          event.stopPropagation();
          closeComposer();
        }}
      >
        <input
          type="text"
          value={note}
          maxLength={NOTE_MAX_CHARS}
          disabled={phase === "busy"}
          // The note is OPTIONAL — a short remark, never content.
          placeholder="a note for the loop (optional)"
          aria-label="A note for the diligence flag (optional)"
          autoFocus
          onChange={(e) => setNote(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") void flag();
          }}
          className="w-44 rounded-hog border border-rule bg-ice-0 px-1.5 py-0.5 font-mono text-xxs text-ink dark:border-charcoal-1 dark:bg-charcoal-2 dark:text-bright"
        />
        <button
          type="button"
          onClick={() => void flag()}
          disabled={phase === "busy"}
          className="font-mono text-sun-deep underline-offset-2 hover:underline disabled:opacity-50 dark:text-sun"
        >
          {phase === "busy" ? "flagging…" : "flag"}
        </button>
        <button
          type="button"
          onClick={closeComposer}
          disabled={phase === "busy"}
          className="font-mono text-shadow-1 hover:text-ink dark:text-moonlight dark:hover:text-bright"
          aria-label="Cancel the flag"
        >
          ×
        </button>
        {phase === "error" && (
          <span className="font-mono text-xxs text-emperor" role="alert">
            {reason ?? "the flag was refused"}
          </span>
        )}
      </span>
    );
  }

  return (
    <button
      type="button"
      ref={triggerRef}
      data-diligence-flag={node.node_id}
      onClick={() => setPhase("composing")}
      className="font-mono underline decoration-dotted underline-offset-2 transition-colors hover:text-ink dark:hover:text-bright"
      title="Flag this for autonomous diligence — the loop picks it up from your queue"
    >
      flag for diligence
    </button>
  );
}
