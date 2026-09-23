import { useState } from "react";

import { track } from "../../lib/analytics";
import { ingestVoiceNote } from "../../lib/api";
import { ingestVerdict } from "../../lib/ingestVerdict";
import { LemonButton } from "../../components/lemon/LemonButton";

type RecordingState = "idle" | "recording" | "transcribing" | "ingested";

/**
 * Quick voice-note capture widget. Lives at the bottom of the
 * DeliverableSidebar panel. Posts a typed `voice_note.ingested`
 * event with the operator's transcript as a flat document; the
 * audio→whisper round trip stays a Sprint-13-end stretch (no
 * audio-upload endpoint yet — the operator pastes the transcript
 * for now).
 *
 * The response is read through the shared ingest verdict: only a note the
 * backend actually chunked counts as ingested. A note skipped with no chunks
 * written (too short to keep) gets a plain not-added message and the
 * transcript stays in the box, so the operator can extend it and try again.
 */
export function VoiceNoteCapture() {
  const [state, setState] = useState<RecordingState>("idle");
  const [transcript, setTranscript] = useState("");
  const [lastDocId, setLastDocId] = useState<string | null>(null);
  const [notAdded, setNotAdded] = useState<string | null>(null);

  async function handleIngest() {
    if (!transcript.trim()) return;
    setState("transcribing");
    setNotAdded(null);
    try {
      const r = await ingestVoiceNote({ transcript: transcript.trim() });
      const verdict = ingestVerdict(r, "your voice note");
      if (verdict.kind !== "absorbed") {
        setNotAdded(
          verdict.kind === "not_added"
            ? verdict.why
            : "The voice note could not be added.",
        );
        setState("idle");
        return;
      }
      track("voice_note_ingested");
      setLastDocId(r.document_id);
      setState("ingested");
      setTranscript("");
    } catch {
      setState("idle");
    }
  }

  return (
    <div className="bg-ice-0 dark:bg-charcoal-2 border border-rule dark:border-charcoal-1 rounded-md p-3">
      <p className="text-xs font-semibold text-ink dark:text-bright uppercase tracking-wide">
        Quick voice note
      </p>
      <p className="mt-1 text-xs text-shadow-1 dark:text-moonlight">
        Paste a transcript (or use the browser dictation button on iOS /
        macOS) to add a voice note straight into the graph.
      </p>
      <textarea
        value={transcript}
        onChange={(e) => setTranscript(e.target.value)}
        rows={3}
        placeholder="Transcript…"
        className="mt-2 w-full px-2 py-1.5 text-sm border border-rule dark:border-charcoal-1 rounded focus:outline-none focus:ring-2 focus:ring-sun"
      />
      <div className="mt-2 flex items-center justify-between gap-2">
        <LemonButton
          variant="primary"
          size="sm"
          onClick={handleIngest}
          disabled={state === "transcribing" || !transcript.trim()}
        >
          {state === "transcribing" ? "Ingesting…" : "Add voice note"}
        </LemonButton>
        {state === "ingested" && lastDocId && (
          <span
            className="text-xs text-success truncate"
            title={lastDocId}
          >
            ✓ {lastDocId.slice(0, 16)}…
          </span>
        )}
      </div>
      {notAdded && (
        <p role="status" className="mt-2 text-xs text-shadow-1 dark:text-moonlight">
          {notAdded}
        </p>
      )}
    </div>
  );
}

export default VoiceNoteCapture;
