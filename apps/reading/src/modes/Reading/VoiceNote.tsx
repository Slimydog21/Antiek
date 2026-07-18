import { useEffect, useState } from "react";

import { LemonButton, LemonTextarea } from "../../components/lemon";
import { saveVoiceNote, transcribeAudio } from "../../api/books";
import { useVoiceRecorder } from "../../hooks/useVoiceRecorder";
import { emitWernerExperience } from "../../werner/reactionBus";

/**
 * VoiceNote (Read SPR-06) — capture a spoken note about the current page,
 * transcribe it, let the reader CORRECT the transcript, then distill it
 * into anchored insight/question notes.
 *
 * The correction step is the honesty guard surfaced in the UI: ASR
 * mishears accents/jargon/names, so the reader confirms or fixes the
 * transcript before it becomes a note (the server also refuses an
 * unconfirmed transcript). Mic-permission-denied degrades to a clear
 * message, never a crash — and the reader can still type.
 */

export interface VoiceNoteProps {
  documentId: string;
  pageIndex: number;
  investigationId: string;
  onSaved?: (noteCount: number) => void;
}

type Phase = "capture" | "transcribing" | "correcting" | "saving" | "saved";

export default function VoiceNote({ documentId, pageIndex, investigationId, onSaved }: VoiceNoteProps) {
  const recorder = useVoiceRecorder();
  const [phase, setPhase] = useState<Phase>("capture");
  const [transcript, setTranscript] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [savedCount, setSavedCount] = useState(0);

  // When a recording finishes, transcribe it.
  useEffect(() => {
    if (recorder.state !== "stopped" || !recorder.blob) return;
    let cancelled = false;
    setPhase("transcribing");
    setError(null);
    (async () => {
      try {
        const res = await transcribeAudio(recorder.blob as Blob);
        if (cancelled) return;
        setTranscript(res.transcript);
        setPhase("correcting");
      } catch (e: unknown) {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : String(e));
        setPhase("correcting"); // let the reader type the note manually
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [recorder.state, recorder.blob]);

  const save = async () => {
    if (!transcript.trim()) return;
    setPhase("saving");
    setError(null);
    try {
      const res = await saveVoiceNote(documentId, {
        page_index: pageIndex,
        transcript: transcript.trim(),
        investigation_id: investigationId,
      });
      setSavedCount(res.note_count);
      setPhase("saved");
      // Living-TV: a confirmed voice note is a noted craft beat.
      emitWernerExperience("note_saved");
      onSaved?.(res.note_count);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
      setPhase("correcting");
    }
  };

  const restart = () => {
    recorder.reset();
    setTranscript("");
    setError(null);
    setPhase("capture");
  };

  return (
    <div className="border border-rule dark:border-charcoal-1 rounded-md p-3 space-y-2 bg-ice-1 dark:bg-charcoal-2">
      <p className="text-[10px] font-mono uppercase tracking-wide text-shadow-1 dark:text-moonlight">
        Voice note · page {pageIndex + 1}
      </p>

      {phase === "capture" && (
        <div className="flex items-center gap-2">
          {recorder.state === "recording" ? (
            <LemonButton type="button" variant="danger" size="sm" onClick={recorder.stop}>
              ■ Stop
            </LemonButton>
          ) : (
            <LemonButton type="button" variant="secondary" size="sm" onClick={() => void recorder.start()}>
              ● Record a thought
            </LemonButton>
          )}
          {recorder.error && (
            <span className="text-[11px] font-mono text-emperor" role="alert">
              {recorder.error}
            </span>
          )}
        </div>
      )}

      {phase === "transcribing" && (
        <p className="text-xs font-mono text-shadow-1 dark:text-moonlight italic">Transcribing…</p>
      )}

      {phase === "correcting" && (
        <div className="space-y-2">
          <p className="text-[11px] font-mono text-shadow-1 dark:text-moonlight">
            Check the transcript before saving — fix any misheard words.
          </p>
          <LemonTextarea
            value={transcript}
            onChange={(e) => setTranscript(e.target.value)}
            placeholder="Your transcribed note — edit freely"
            rows={3}
            aria-label="Voice note transcript (editable)"
          />
          {error && (
            <span className="text-[11px] font-mono text-emperor" role="alert">
              {error}
            </span>
          )}
          <div className="flex items-center gap-2">
            <LemonButton type="button" variant="primary" size="sm" disabled={!transcript.trim()} onClick={() => void save()}>
              Save note
            </LemonButton>
            <LemonButton type="button" variant="tertiary" size="sm" onClick={restart}>
              Re-record
            </LemonButton>
          </div>
        </div>
      )}

      {phase === "saving" && (
        <p className="text-xs font-mono text-shadow-1 dark:text-moonlight italic">Distilling into notes…</p>
      )}

      {phase === "saved" && (
        <div className="flex items-center gap-2">
          <p className="text-xs text-ink dark:text-bright">
            Saved — {savedCount} {savedCount === 1 ? "note" : "notes"} distilled from this thought.
          </p>
          <LemonButton type="button" variant="tertiary" size="sm" onClick={restart}>
            Another
          </LemonButton>
        </div>
      )}
    </div>
  );
}
