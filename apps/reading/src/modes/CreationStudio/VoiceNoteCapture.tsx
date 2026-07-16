import { useState } from "react";

import { track } from "../../lib/analytics";
import { ingestVoiceNote } from "../../lib/api";
import { emitWernerExperience } from "../../werner/reactionBus";

type RecordingState = "idle" | "recording" | "transcribing" | "ingested";

/**
 * Quick voice-note capture widget. Lives at the bottom of the
 * DeliverableSidebar panel. Posts a typed `voice_note.ingested`
 * event with the operator's transcript as a flat document; the
 * audio→whisper round trip stays a Sprint-13-end stretch (no
 * audio-upload endpoint yet — the operator pastes the transcript
 * for now).
 */
export function VoiceNoteCapture() {
  const [state, setState] = useState<RecordingState>("idle");
  const [transcript, setTranscript] = useState("");
  const [lastDocId, setLastDocId] = useState<string | null>(null);

  async function handleIngest() {
    if (!transcript.trim()) return;
    setState("transcribing");
    try {
      const r = await ingestVoiceNote({ transcript: transcript.trim() });
      track("voice_note_ingested");
      setLastDocId(r.document_id);
      setState("ingested");
      setTranscript("");
      // Living-TV: user-sourced voice note into the graph — noted beat.
      emitWernerExperience("note_saved");
    } catch {
      emitWernerExperience("fail");
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
        <button
          onClick={handleIngest}
          disabled={state === "transcribing" || !transcript.trim()}
          className="px-3 py-1.5 bg-ink hover:bg-shadow-2 disabled:bg-glacial-1 dark:bg-slate-1 text-white text-xs rounded"
        >
          {state === "transcribing" ? "Ingesting…" : "Add voice note"}
        </button>
        {state === "ingested" && lastDocId && (
          <span
            className="text-xs text-aurora truncate"
            title={lastDocId}
          >
            ✓ {lastDocId.slice(0, 16)}…
          </span>
        )}
      </div>
    </div>
  );
}

export default VoiceNoteCapture;
