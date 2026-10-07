import { useEffect, useRef, useState } from "react";

import LemonButton from "../../components/lemon/LemonButton";
import { registerKeyboardOwner } from "../../workspace/keyboardOwnership";
import { transcribeAudio, ApiError } from "../../lib/api";
import { useVoiceRecorder } from "../../hooks/useVoiceRecorder";
import AIActionFailure from "../../shared/AIActionFailure";

/**
 * VoiceChaseButton — drive a chase by voice (SPR-04 M4).
 *
 * Reuses the SHIPPED capture path (``useVoiceRecorder`` →
 * ``POST /voice/transcribe``); it does not rebuild recording or
 * transcription. Record a thought, it transcribes, and the transcript is
 * handed to the parent (``onTranscript``) as the chase question — the
 * reader still edits it before launching, the same correct-before-commit
 * guard the reader voice-note flow uses.
 *
 * Honest no-key (M4): transcription is gated on the operator OpenAI key.
 * Without it the endpoint returns 503; we surface the shared
 * ``AIActionFailure`` no-result state rather than a fabricated transcript.
 * Mic-permission-denied degrades to a clear line (the reader can still
 * type), never a crash.
 */
type Props = {
  onTranscript: (transcript: string) => void;
  disabled?: boolean;
  /** Idle button text. Defaults to the chase copy. */
  idleLabel?: string;
  /** FFX-KPA SPR-03 M4: Escape while recording cancels — the take is
   *  discarded, nothing is sent to /voice/transcribe. Opt-in so the existing
   *  hosts keep their behaviour. */
  escapeCancels?: boolean;
  /** Told when recording starts and ends, so a host can give Escape to the
   *  recorder while it runs. */
  onRecordingChange?: (recording: boolean) => void;
};

type Phase = "idle" | "transcribing" | "error";

export default function VoiceChaseButton({
  onTranscript,
  disabled,
  idleLabel = "● Say it instead",
  escapeCancels = false,
  onRecordingChange,
}: Props) {
  const recorder = useVoiceRecorder();
  const cancelledRef = useRef(false);
  const recording = recorder.state === "recording";

  useEffect(() => {
    onRecordingChange?.(recording);
  }, [recording, onRecordingChange]);

  useEffect(() => {
    if (!escapeCancels || !recording) return;
    return registerKeyboardOwner(window, {
      id: "voice.escape-cancel", scope: "overlay",
      eligible: (e) => e.key === "Escape",
    }, (e) => {
      e.preventDefault();
      cancelledRef.current = true;
      recorder.stop();
    });
  }, [escapeCancels, recording, recorder.stop]);
  const [phase, setPhase] = useState<Phase>("idle");
  // null reason ⇒ the no-key case (AIActionFailure says so); a string ⇒ a
  // specific transient the engine reported.
  const [failure, setFailure] = useState<{ reason: string | null } | null>(null);

  // When a recording finishes, transcribe it and hand the text up.
  useEffect(() => {
    if (recorder.state !== "stopped" || !recorder.blob) return;
    if (cancelledRef.current) {
      // Escape-cancelled take: discard it without transcribing.
      cancelledRef.current = false;
      recorder.reset();
      return;
    }
    let cancelled = false;
    setPhase("transcribing");
    setFailure(null);
    void (async () => {
      try {
        const res = await transcribeAudio(recorder.blob as Blob);
        if (cancelled) return;
        onTranscript(res.transcript);
        setPhase("idle");
        recorder.reset();
      } catch (e) {
        if (cancelled) return;
        // 503 = no provider key (the common no-key case → null reason so
        // AIActionFailure shows the "model provider isn't configured"
        // sentence). Any other status carries the engine's reason.
        const status = e instanceof ApiError ? e.status : 0;
        const reason =
          status === 503
            ? null
            : e instanceof Error
              ? e.message
              : String(e);
        setFailure({ reason });
        setPhase("error");
      }
    })();
    return () => {
      cancelled = true;
    };
    // recorder.reset is stable; depend on the capture signal only.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [recorder.state, recorder.blob]);

  const retry = () => {
    recorder.reset();
    setFailure(null);
    setPhase("idle");
  };

  if (phase === "error" && failure) {
    return (
      <AIActionFailure
        title="Couldn’t turn that into a question"
        reason={failure.reason}
        onRetry={retry}
        retryLabel="Record again"
      />
    );
  }

  return (
    <div className="flex items-center gap-2">
      {recorder.state === "recording" ? (
        <LemonButton type="button" variant="danger" size="sm" onClick={recorder.stop}>
          ■ Stop
        </LemonButton>
      ) : (
        <LemonButton
          type="button"
          variant="tertiary"
          size="sm"
          disabled={disabled || phase === "transcribing"}
          onClick={() => void recorder.start()}
        >
          {phase === "transcribing" ? "Listening…" : idleLabel}
        </LemonButton>
      )}
      {recorder.error && (
        <span className="text-xs font-mono text-shadow-1 dark:text-moonlight" role="alert">
          {recorder.error}
        </span>
      )}
    </div>
  );
}
