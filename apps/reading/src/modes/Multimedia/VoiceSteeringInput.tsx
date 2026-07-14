import { useEffect, useRef, useState } from "react";

import { transcribe } from "../../api/asr";
import { LemonButton, LemonTextarea } from "../../components/lemon";
import { useVoiceRecorder } from "../../hooks/useVoiceRecorder";

type CapturePhase = "idle" | "requesting" | "transcribing" | "review" | "error";
const HAS_WORD_CHARACTER = /[\p{L}\p{N}]/u;

export function VoiceSteeringInput({
  value,
  rawTranscript,
  disabled,
  onChange,
  onTranscript,
  onDiscardTranscript,
  onBusyChange,
}: {
  value: string;
  rawTranscript: string | null;
  disabled: boolean;
  onChange: (value: string) => void;
  onTranscript: (rawTranscript: string) => void;
  onDiscardTranscript: () => void;
  onBusyChange: (busy: boolean) => void;
}) {
  const recorder = useVoiceRecorder();
  const processedBlob = useRef<Blob | null>(null);
  const onTranscriptRef = useRef(onTranscript);
  const [phase, setPhase] = useState<CapturePhase>("idle");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    onTranscriptRef.current = onTranscript;
  }, [onTranscript]);

  useEffect(() => {
    if (recorder.state !== "stopped" || !recorder.blob || processedBlob.current === recorder.blob) return;
    const blob = recorder.blob;
    processedBlob.current = blob;
    let cancelled = false;
    setPhase("transcribing");
    setError(null);
    const abortController = new AbortController();
    transcribe(blob, { signal: abortController.signal })
      .then((result) => {
        if (cancelled) return;
        const transcript = result.transcript.trim();
        if (!HAS_WORD_CHARACTER.test(transcript)) {
          setPhase("error");
          setError("No words were detected. Type the steer or record again.");
          return;
        }
        onTranscriptRef.current(transcript);
        setPhase("review");
      })
      .catch((caught: unknown) => {
        if (cancelled) return;
        setPhase("error");
        setError(caught instanceof Error ? caught.message : "Voice transcription failed. Type the steer instead.");
      });
    return () => {
      cancelled = true;
      abortController.abort();
    };
  }, [recorder.blob, recorder.state]);

  useEffect(() => () => {
    if (recorder.state === "recording") recorder.stop();
  }, [recorder.state, recorder.stop]);

  useEffect(() => {
    if (phase === "requesting" && recorder.state !== "idle") setPhase("idle");
  }, [phase, recorder.state]);

  function toggleRecording() {
    setError(null);
    if (recorder.state === "recording") {
      recorder.stop();
      return;
    }
    processedBlob.current = null;
    recorder.reset();
    setPhase("requesting");
    void recorder.start();
  }

  const isRecording = recorder.state === "recording";
  const busy = isRecording || phase === "requesting" || phase === "transcribing";
  const recorderError = recorder.state === "denied"
    ? "Microphone permission was denied. You can still type a steer."
    : recorder.error;
  const announcement = isRecording
    ? "Recording voice steering."
    : phase === "requesting"
      ? "Requesting microphone access."
      : phase === "transcribing"
        ? "Transcribing voice steering."
        : phase === "review"
          ? "Voice transcript ready for review."
          : "";

  useEffect(() => {
    onBusyChange(busy);
  }, [busy, onBusyChange]);

  useEffect(() => () => onBusyChange(false), [onBusyChange]);

  return (
    <div>
      <span className="sr-only" role="status" aria-live="polite">{announcement}</span>
      <p className="font-mono text-[12px] text-shadow-2 dark:text-moonlight">Text or voice steering</p>
      <LemonTextarea
        value={value}
        minRows={3}
        maxRows={5}
        onChange={(event) => onChange(event.target.value)}
        aria-label="Steering prompt"
        className="mt-2"
      />
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <LemonButton
          type="button"
          size="sm"
          variant="tertiary"
          icon={<span aria-hidden="true">{isRecording ? "■" : "●"}</span>}
          disabled={disabled || phase === "requesting" || phase === "transcribing"}
          onClick={toggleRecording}
          aria-pressed={isRecording}
        >
          {isRecording
            ? "Stop recording"
            : phase === "requesting"
              ? "Requesting microphone..."
              : phase === "transcribing"
                ? "Transcribing..."
                : "Record voice"}
        </LemonButton>
        {rawTranscript && (
          <>
            <span className="font-mono text-[11px] text-shadow-1 dark:text-moonlight" role="status">
              Voice transcript attached. Review before applying.
            </span>
            <LemonButton type="button" size="sm" variant="tertiary" onClick={onDiscardTranscript} disabled={disabled || busy}>
              Discard voice
            </LemonButton>
          </>
        )}
      </div>
      {(error || recorderError) && (
        <p className="mt-2 text-[12px] text-emperor" role="alert">{error || recorderError}</p>
      )}
    </div>
  );
}

export default VoiceSteeringInput;
