import { useCallback, useRef, useState } from "react";

import LemonButton from "../../components/lemon/LemonButton";
import {
  ingestSource,
  ingestVoiceNote,
  ApiError,
} from "../../lib/api";
import AIActionFailure from "../../shared/AIActionFailure";
import { emitWernerExperience } from "../../werner/reactionBus";

/**
 * PasteIngest — drop or paste a file / URL / passage into a research and
 * have it absorbed (SPR-04 M3).
 *
 * It wires the gesture to the SHIPPED universal-ingest paths; it builds no
 * new ingest substrate:
 *   - a pasted/dropped URL → POST /sources/ingest (auto-detects
 *     arxiv / youtube / podcast / url) — the universal URL ingest.
 *   - pasted text or a dropped text/markdown file → POST /voice-notes/ingest,
 *     the shipped text→document path (chunked + provenance-stamped via the
 *     voice acquisition adapter; despite the "voice" name it is the
 *     substrate's text-as-flat-document ingest).
 * Each lands a real document with chunks, so it is reachable by a
 * subsequent synthesis run / chase as a NAMED source (M1).
 *
 * Honest about what the shipped path can NOT do (rigor #1 + #3): a binary
 * file the browser can't read as text (a true PDF blob) has no shipped
 * multipart endpoint here, so we reject it plainly rather than pretend to
 * absorb it. The reader is told to paste a link to it or its text instead.
 *
 * Max-context bound (rigor #3 + #5): the synthesis context is bounded at
 * SYNTHESIS_CONTEXT_BUDGET_TOKENS (substrate/constants.py = 256_000). If a
 * pasted blob is plainly larger than that pack can hold, we say so up
 * front — the synthesis will use what fits — rather than imply all of it
 * lands in context. We do not silently truncate.
 */

// Mirror of substrate/constants.py:SYNTHESIS_CONTEXT_BUDGET_TOKENS. The
// authoritative bound + truncation live server-side at pack assembly; this
// copy only powers an honest up-front warning. Keep in sync with the
// constant (there is no codegen for plain ints today).
const SYNTHESIS_CONTEXT_BUDGET_TOKENS = 256_000;
// A deliberately rough chars→tokens estimate (~4 chars/token for English
// prose). Used only to decide whether to WARN; never to truncate.
const APPROX_CHARS_PER_TOKEN = 4;

type Outcome =
  | { kind: "idle" }
  | { kind: "absorbing" }
  | { kind: "absorbed"; title: string; oversize: boolean }
  | { kind: "rejected"; why: string }
  | { kind: "failed"; reason: string | null };

const TEXT_EXTENSIONS = /\.(txt|md|markdown|csv|json|log|rtf)$/i;

export default function PasteIngest({
  investigationId,
}: {
  investigationId: string;
}) {
  const [outcome, setOutcome] = useState<Outcome>({ kind: "idle" });
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const exceedsContext = useCallback((text: string): boolean => {
    const approxTokens = text.length / APPROX_CHARS_PER_TOKEN;
    return approxTokens > SYNTHESIS_CONTEXT_BUDGET_TOKENS;
  }, []);

  const absorbText = useCallback(
    async (text: string, title: string) => {
      setOutcome({ kind: "absorbing" });
      try {
        const r = await ingestVoiceNote({
          transcript: text,
          investigation_id: investigationId,
          title,
        });
        setOutcome({
          kind: "absorbed",
          title: r.title ?? title,
          oversize: exceedsContext(text),
        });
        // Living-TV: corpus absorb is a curious highlight glance.
        emitWernerExperience("highlight");
      } catch (e) {
        const reason = e instanceof ApiError ? e.body || null : null;
        setOutcome({ kind: "failed", reason });
        emitWernerExperience("fail");
      }
    },
    [investigationId, exceedsContext],
  );

  const absorbUrl = useCallback(
    async (url: string) => {
      setOutcome({ kind: "absorbing" });
      try {
        const r = await ingestSource({ url, investigation_id: investigationId });
        if (r.status === "error") {
          setOutcome({ kind: "failed", reason: r.error_message });
          emitWernerExperience("fail");
          return;
        }
        setOutcome({
          kind: "absorbed",
          title: r.title ?? url,
          oversize: false,
        });
        emitWernerExperience("highlight");
      } catch (e) {
        const reason = e instanceof ApiError ? e.body || null : null;
        setOutcome({ kind: "failed", reason });
        emitWernerExperience("fail");
      }
    },
    [investigationId],
  );

  /** Route a pasted/typed string: a bare URL goes to the URL ingest, any
   *  other text goes to the text→document ingest. */
  const handleString = useCallback(
    (raw: string) => {
      const s = raw.trim();
      if (!s) return;
      if (/^https?:\/\/\S+$/i.test(s)) {
        void absorbUrl(s);
      } else {
        void absorbText(s, `Pasted note · ${new Date().toLocaleString()}`);
      }
    },
    [absorbUrl, absorbText],
  );

  /** Route a dropped/selected file. Text-like files are read and ingested;
   *  a binary file the browser can't read as text is rejected honestly. */
  const handleFile = useCallback(
    async (file: File) => {
      if (!TEXT_EXTENSIONS.test(file.name) && !file.type.startsWith("text/")) {
        setOutcome({
          kind: "rejected",
          why:
            `“${file.name}” isn’t a kind I can absorb directly yet. ` +
            "Paste a link to it, or paste its text.",
        });
        return;
      }
      const text = await file.text();
      await absorbText(text, file.name);
    },
    [absorbText],
  );

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragOver(false);
      const file = e.dataTransfer.files?.[0];
      if (file) {
        void handleFile(file);
        return;
      }
      const text = e.dataTransfer.getData("text");
      if (text) handleString(text);
    },
    [handleFile, handleString],
  );

  const onPaste = useCallback(
    (e: React.ClipboardEvent) => {
      const file = e.clipboardData.files?.[0];
      if (file) {
        e.preventDefault();
        void handleFile(file);
        return;
      }
      const text = e.clipboardData.getData("text");
      if (text) {
        e.preventDefault();
        handleString(text);
      }
    },
    [handleFile, handleString],
  );

  return (
    <div className="border border-dashed border-rule dark:border-charcoal-1 rounded-md p-3 bg-ice-1 dark:bg-charcoal-2">
      <p className="text-[10px] font-mono uppercase tracking-wide text-shadow-1 dark:text-moonlight">
        Add to this research
      </p>
      <div
        role="button"
        tabIndex={0}
        onPaste={onPaste}
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={onDrop}
        onClick={() => fileInputRef.current?.click()}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") fileInputRef.current?.click();
        }}
        className={
          "mt-2 rounded-md px-3 py-4 text-center text-sm cursor-text transition-colors " +
          (dragOver
            ? "bg-sun/10 text-ink dark:text-bright"
            : "text-shadow-1 dark:text-moonlight hover:bg-ice-2 dark:hover:bg-charcoal-1")
        }
      >
        {outcome.kind === "absorbing"
          ? "Absorbing…"
          : "Drop a file, paste a link, or paste a passage."}
      </div>
      <input
        ref={fileInputRef}
        type="file"
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) void handleFile(f);
          e.target.value = "";
        }}
      />

      {outcome.kind === "absorbed" && (
        <div className="mt-2 text-xs">
          <p className="text-aurora" role="status">
            Absorbed <span className="font-semibold">{outcome.title}</span>. It
            can be cited the next time this research runs.
          </p>
          {outcome.oversize && (
            <p className="mt-1 text-sun-deep dark:text-sun">
              It’s larger than the research can hold in one pass — the
              synthesis will use the most relevant parts, not the whole thing.
            </p>
          )}
        </div>
      )}

      {outcome.kind === "rejected" && (
        <p className="mt-2 text-xs text-shadow-1 dark:text-moonlight" role="status">
          {outcome.why}
        </p>
      )}

      {outcome.kind === "failed" && (
        <div className="mt-2">
          <AIActionFailure
            title="Couldn’t absorb that"
            reason={outcome.reason}
            onRetry={() => setOutcome({ kind: "idle" })}
            retryLabel="Dismiss"
          />
        </div>
      )}

      <div className="mt-2 flex justify-end">
        <LemonButton
          size="sm"
          variant="tertiary"
          onClick={() => fileInputRef.current?.click()}
          disabled={outcome.kind === "absorbing"}
        >
          Choose a file
        </LemonButton>
      </div>
    </div>
  );
}
