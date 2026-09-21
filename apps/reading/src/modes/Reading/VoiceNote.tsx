import { useEffect, useState } from "react";

import { LemonButton, LemonTextarea } from "../../components/lemon";
import { saveVoiceNote, transcribeAudio } from "../../api/books";
import {
  THOUGHT_PARTNER_SEED_EVENT,
  composeThoughtPartnerSystemContext,
} from "../../components/ai/thoughtPartnerSeed";
import { useVoiceRecorder } from "../../hooks/useVoiceRecorder";

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
 *
 * After save, question-shaped parks seed the Thought Partner bus with
 * the SERVABLE reading mount (composeThoughtPartnerSystemContext) so
 * discuss stays on the reading path (voice → park → discuss).
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
  const [parkedTexts, setParkedTexts] = useState<string[]>([]);
  const [parkedIds, setParkedIds] = useState<string[]>([]);

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

  const seedThoughtPartner = (texts: string[], ids: string[]) => {
    const q = (texts[0] || "").trim();
    if (!q) return;
    const qid = ids[0] || "voice";
    window.dispatchEvent(
      new CustomEvent(THOUGHT_PARTNER_SEED_EVENT, {
        detail: {
          prompt:
            `Discuss this parked question from a voice note — challenge, synthesize, or extend:\n\n${q}`,
          system_context: composeThoughtPartnerSystemContext(),
          source_label: `voice-park · ${qid} · p.${pageIndex + 1}`,
        },
      }),
    );
  };

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
      const texts = res.parked_question_texts ?? [];
      const ids = res.parked_question_ids ?? [];
      setParkedTexts(texts);
      setParkedIds(ids);
      setPhase("saved");
      onSaved?.(res.note_count);
      // Auto-seed TP when something parked — reading mount included.
      if (texts.length > 0) {
        seedThoughtPartner(texts, ids);
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
      setPhase("correcting");
    }
  };

  const restart = () => {
    recorder.reset();
    setTranscript("");
    setError(null);
    setParkedTexts([]);
    setParkedIds([]);
    setPhase("capture");
  };

  return (
    <div className="border border-rule dark:border-charcoal-1 rounded-md p-3 space-y-2 bg-ice-1 dark:bg-charcoal-2">
      <p className="text-xxs font-mono uppercase tracking-wide text-shadow-1 dark:text-moonlight">
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
            <span className="text-xs font-mono text-emperor" role="alert">
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
          <p className="text-xs font-mono text-shadow-1 dark:text-moonlight">
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
            <span className="text-xs font-mono text-emperor" role="alert">
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
        <div className="space-y-2">
          <div className="flex items-center gap-2 flex-wrap">
            <p className="text-xs text-ink dark:text-bright">
              Saved — {savedCount} {savedCount === 1 ? "note" : "notes"} distilled
              {parkedTexts.length > 0
                ? ` · ${parkedTexts.length} parked for discuss`
                : ""}.
            </p>
            <LemonButton type="button" variant="tertiary" size="sm" onClick={restart}>
              Another
            </LemonButton>
          </div>
          {parkedTexts.length > 0 && (
            <div className="flex items-center gap-2 flex-wrap">
              <LemonButton
                type="button"
                variant="secondary"
                size="sm"
                onClick={() => seedThoughtPartner(parkedTexts, parkedIds)}
              >
                Discuss in Thought Partner
              </LemonButton>
              <span className="text-xxs font-mono text-shadow-1 dark:text-moonlight">
                Seeds Surface E / sidecar with this page&apos;s reading mount
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
