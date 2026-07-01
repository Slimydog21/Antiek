import { useState } from "react";

import { track } from "../../lib/analytics";
import { ingestVoiceNote } from "../../lib/api";
import { useVoiceCapture, type VoiceCaptureResult } from "../../hooks/useVoiceCapture";

type RecordingState = "idle" | "ingesting" | "ingested";

/**
 * Quick voice-note capture widget. Lives at the bottom of the
 * DeliverableSidebar panel. It composes the shared voice-in path
 * (`useVoiceCapture` → `/voice/blob` + `/voice/transcribe` + `voice.captured`)
 * with the single owner of voice-note documents (`ingestVoiceNote`). The
 * transcript always stays editable before ingest because ASR is a draft, not a
 * source of truth.
 */
export function VoiceNoteCapture({
  investigationId = "creation-studio",
}: {
  investigationId?: string;
}) {
  const [state, setState] = useState<RecordingState>("idle");
  const [transcript, setTranscript] = useState("");
  const [captured, setCaptured] = useState<VoiceCaptureResult | null>(null);
  const [lastDocId, setLastDocId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const voice = useVoiceCapture();

  async function handleIngest() {
    if (!transcript.trim()) return;
    setState("ingesting");
    setError(null);
    try {
      const r = await ingestVoiceNote({
        transcript: transcript.trim(),
        investigation_id: investigationId,
        duration_seconds: captured?.durationSeconds,
        language: captured?.language ?? undefined,
      });
      track("voice_note_ingested");
      setLastDocId(r.document_id);
      setState("ingested");
      setTranscript("");
      setCaptured(null);
    } catch {
      setError("Couldn’t add that voice note. Try again.");
      setState("idle");
    }
  }

  async function handleVoiceCapture() {
    setError(null);
    try {
      if (voice.phase === "recording") {
        const result = await voice.stopAndCapture({ investigationId });
        if (!result) return;
        if (result.transcriptStatus === "empty") {
          setError("No words were captured. You can still type the note.");
          return;
        }
        setCaptured(result);
        setTranscript((prev) =>
          prev.trim() ? `${prev.trim()}\n${result.transcript}` : result.transcript,
        );
        return;
      }
      await voice.start();
    } catch {
      setError("Could not capture voice. Try again.");
    }
  }

  const voiceBusy = voice.phase === "transcribing" || voice.phase === "persisting";

  return (
    <div className="bg-ice-0 dark:bg-charcoal-2 border border-rule dark:border-charcoal-1 rounded-md p-3">
      <p className="text-xs font-semibold text-ink dark:text-bright uppercase tracking-wide">
        Quick voice note
      </p>
      <p className="mt-1 text-xs text-shadow-1 dark:text-moonlight">
        Record a thought or paste a transcript, then check the words before
        adding it to the graph.
      </p>
      <textarea
        value={transcript}
        onChange={(e) => setTranscript(e.target.value)}
        rows={3}
        placeholder="Transcript…"
        className="mt-2 w-full px-2 py-1.5 text-sm border border-rule dark:border-charcoal-1 rounded focus:outline-none focus:ring-2 focus:ring-sun"
      />
      {voice.recorderState === "denied" ? (
        <p className="mt-1 text-[11px] font-mono text-emperor" role="alert">
          Microphone permission was denied. You can still paste a transcript.
        </p>
      ) : null}
      {(voice.recorderState !== "denied" && voice.error) || error ? (
        <p className="mt-1 text-[11px] font-mono text-emperor" role="alert">
          {voice.error ?? error}
        </p>
      ) : null}
      <div className="mt-2 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => void handleVoiceCapture()}
            disabled={voiceBusy || state === "ingesting"}
            className="px-3 py-1.5 border border-rule dark:border-charcoal-1 text-xs rounded hover:bg-ice-2 disabled:opacity-50"
          >
            {voice.phase === "recording"
              ? "Stop recording"
              : voiceBusy
                ? "Listening…"
                : "Record"}
          </button>
          {captured?.audioRef ? (
            <span className="text-[10px] font-mono text-shadow-1 dark:text-moonlight">
              voice saved
            </span>
          ) : null}
        </div>
        <button
          onClick={handleIngest}
          disabled={state === "ingesting" || voiceBusy || !transcript.trim()}
          className="px-3 py-1.5 bg-ink hover:bg-shadow-2 disabled:bg-glacial-1 dark:bg-slate-1 text-white text-xs rounded"
        >
          {state === "ingesting" ? "Ingesting…" : "Add voice note"}
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
