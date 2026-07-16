import { useState, type FormEvent } from "react";

import type { DistillationRequestedPayload } from "../generated/types";
import { postTypedEvent } from "../lib/api";
import { emitWernerExperience } from "../werner/reactionBus";

interface ChatInputProps {
  investigationId: string;
  documentId: string | null;
  /** The most recently selected region. Null when nothing's selected
   *  yet (or no document loaded). Used as the scope of the distillation
   *  request; when null, the request is whole-document scoped. */
  region: {
    region_id: string;
    page: number | null;
    text_excerpt: string;
  } | null;
  /** Render in disabled state while no document is loaded. */
  disabled: boolean;
}

const TARGET_TOKENS = 512;

export default function ChatInput({
  investigationId,
  documentId,
  region,
  disabled,
}: ChatInputProps) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    const prompt = text.trim();
    if (!prompt) return;

    setBusy(true);
    setError(null);
    const payload: DistillationRequestedPayload = {
      action_type: "distillation.requested",
      region_id: region?.region_id ?? null,
      user_prompt: prompt,
      target_token_count: TARGET_TOKENS,
    };
    try {
      // The wrestling event_type requires document_id on the envelope.
      // We won't reach this branch with documentId=null because the
      // outer ``disabled`` prop covers that case, but assert defensively.
      if (!documentId) {
        throw new Error("no document loaded");
      }
      await postTypedEvent({
        investigation_id: investigationId,
        document_id: documentId,
        payload,
        role: "user_agent",
      });
      setText("");
      // Living-TV: distillation asked of the document — thinking chase.
      emitWernerExperience("deep_research_start");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      emitWernerExperience("fail");
    } finally {
      setBusy(false);
    }
  }

  const placeholder = region
    ? "Ask about the highlighted region…"
    : "Ask about the whole document…";

  return (
    <form
      onSubmit={onSubmit}
      className="border-t border-rule dark:border-charcoal-1 bg-ice-0 dark:bg-charcoal-2 px-3 py-2 flex flex-col gap-1.5"
    >
      {region ? (
        <RegionContextChip region={region} />
      ) : disabled ? null : (
        <div className="text-[10px] font-mono text-ink-mute dark:text-moonlight px-1">
          no region selected — whole-document scope
        </div>
      )}
      <div className="flex gap-2 items-end">
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={placeholder}
          disabled={disabled || busy}
          rows={2}
          className="flex-1 resize-none rounded-md border border-rule dark:border-charcoal-1 px-2.5 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-sun disabled:bg-ice-3 dark:bg-charcoal-1 disabled:text-ink-mute dark:text-moonlight"
          onKeyDown={(e) => {
            // Cmd/Ctrl+Enter submits — matches Cursor's chat ergonomics.
            if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
              onSubmit(e as unknown as FormEvent);
            }
          }}
        />
        <button
          type="submit"
          disabled={disabled || busy || !text.trim()}
          className="self-stretch px-3 text-xs font-medium bg-ink text-white rounded-md hover:bg-shadow-2 disabled:bg-glacial-1 dark:bg-slate-1 disabled:text-shadow-1 dark:text-moonlight transition-colors"
        >
          {busy ? "…" : "ask"}
        </button>
      </div>
      {error && (
        <div className="text-[11px] font-mono text-emperor px-1">{error}</div>
      )}
    </form>
  );
}

function RegionContextChip({
  region,
}: {
  region: NonNullable<ChatInputProps["region"]>;
}) {
  const excerpt =
    region.text_excerpt.length > 90
      ? region.text_excerpt.slice(0, 90) + "…"
      : region.text_excerpt;
  return (
    <div className="text-[10px] font-mono text-shadow-1 dark:text-moonlight px-1 flex items-center gap-1.5 truncate">
      <span className="inline-flex items-center px-1.5 py-0.5 rounded bg-blue-50 text-blue-700">
        region
        {region.page != null && <span className="ml-1">p{region.page}</span>}
      </span>
      <span className="italic truncate" title={region.text_excerpt}>
        "{excerpt}"
      </span>
    </div>
  );
}
