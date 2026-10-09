import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";

import { AsrError, transcribe } from "../../api/asr";
import LemonButton from "../../components/lemon/LemonButton";
import LemonTextarea from "../../components/lemon/LemonTextarea";
import { useVoiceRecorder } from "../../hooks/useVoiceRecorder";

/** A capture keeps its originating owner, pane incarnation and project context. */
export interface AgentVoiceAdmission {
  isCurrent: () => boolean;
  subscribe: (retire: () => void) => () => void;
}

interface Props {
  captureAdmission: () => AgentVoiceAdmission | null;
  onTranscript: (text: string) => boolean;
  onRecordingChange: (recording: boolean) => void;
  registerStop: (stop: () => void) => () => void;
}

type VoicePhase = "requesting" | "recording" | "transcribing" | "review" | "error";
const voiceStatus: Record<VoicePhase, string> = {
  requesting: "Requesting microphone access…",
  recording: "Recording your thought. Stop to review the transcript.",
  transcribing: "Transcribing your thought…",
  review: "Review your words before adding them to the draft.",
  error: "Voice input stopped. Your typed draft is unchanged.",
};

function admitted(admission: AgentVoiceAdmission): boolean {
  try { return admission.isCurrent() === true; }
  catch { return false; }
}

export function AgentVoiceInput(props: Props) {
  const [attempt, setAttempt] = useState<{ id: number; admission: AgentVoiceAdmission } | null>(null);
  const [admissionError, setAdmissionError] = useState<string | null>(null);
  const sequence = useRef(0);
  const finish = useCallback((id: number) => {
    setAttempt((current) => current?.id === id ? null : current);
  }, []);

  if (attempt) return <VoiceAttempt key={attempt.id} {...props} {...attempt} finish={finish} />;
  return (
    <div className="px-3 pb-2 shrink-0">
      <LemonButton variant="tertiary" size="sm" onClick={() => {
        let admission: AgentVoiceAdmission | null;
        try { admission = props.captureAdmission(); }
        catch { admission = null; }
        if (!admission || !admitted(admission)) {
          setAdmissionError("Voice input is unavailable in this pane right now. You can still type.");
          return;
        }
        setAdmissionError(null);
        setAttempt({ id: ++sequence.current, admission });
      }}>
        Record voice
      </LemonButton>
      {admissionError ? <p role="status" className="text-xxs text-shadow-1 dark:text-moonlight">{admissionError}</p> : null}
    </div>
  );
}

/** Each attempt has a fresh recorder hook. A discarded recorder's late final
 * data/stop events cannot touch a new attempt's stream or chunk buffer. */
function VoiceAttempt({ id, admission, finish, ...props }: Props & {
  id: number;
  admission: AgentVoiceAdmission;
  finish: (id: number) => void;
}) {
  const recorder = useVoiceRecorder();
  const [phase, setPhase] = useState<Exclude<VoicePhase, "recording">>("requesting");
  const [transcript, setTranscript] = useState("");
  const [error, setError] = useState<string | null>(null);
  const live = useRef(true);
  const uploaded = useRef<Blob | null>(null);
  const request = useRef<AbortController | null>(null);
  const used = useRef(false);
  const callbacks = useRef(props);
  useLayoutEffect(() => { callbacks.current = props; });
  const current = useCallback(() => live.current && admitted(admission), [admission]);

  const cancel = useCallback(() => {
    if (!live.current) return;
    live.current = false;
    request.current?.abort();
    recorder.reset();
    recorder.stop();
    callbacks.current.onRecordingChange(false);
    finish(id);
  }, [recorder.reset, recorder.stop, finish, id]);

  const stop = useCallback(() => {
    if (!current()) { cancel(); return; }
    recorder.stop();
  }, [current, cancel, recorder.stop]);

  useEffect(() => {
    live.current = true;
    const unsubscribe = admission.subscribe(cancel);
    if (current()) void recorder.start();
    else cancel();
    return () => {
      live.current = false;
      unsubscribe();
      request.current?.abort();
      callbacks.current.onRecordingChange(false);
    };
  }, [admission, current, cancel, recorder.start]);

  useEffect(() => callbacks.current.registerStop(stop), [stop]);

  useEffect(() => {
    if (!current()) return;
    const recording = recorder.state === "recording";
    callbacks.current.onRecordingChange(recording);
  }, [recorder.state, current]);

  useEffect(() => {
    if (recorder.state !== "stopped" || !recorder.blob || uploaded.current === recorder.blob || !current()) return;
    const blob = recorder.blob;
    uploaded.current = blob;
    if (blob.size === 0 || blob.size > 25 * 1024 * 1024) {
      setError(blob.size === 0 ? "No audio was captured. You can record again or type." : "That recording exceeds 25 MiB. Record a shorter thought or type.");
      setPhase("error");
      return;
    }
    const controller = new AbortController();
    request.current = controller;
    setPhase("transcribing");
    void transcribe(blob, { signal: controller.signal }).then((result) => {
      if (!current() || controller.signal.aborted || request.current !== controller) return;
      if (typeof result.transcript !== "string") throw new Error("The server did not return a voice transcript. You can still type.");
      const text = result.transcript.trim();
      if (!/[\p{L}\p{N}]/u.test(text)) throw new Error("No words were detected. Record again or type your thought.");
      setTranscript(text);
      setPhase("review");
    }).catch((caught: unknown) => {
      if (!current() || controller.signal.aborted || request.current !== controller) return;
      setError(caught instanceof AsrError && caught.status === 403
        ? "Voice transcription is restricted to operators on this server. You can still type."
        : caught instanceof Error ? caught.message : "Voice transcription failed. You can still type.");
      setPhase("error");
    });
    return () => controller.abort();
  }, [recorder.state, recorder.blob, current]);

  const recording = recorder.state === "recording";
  const recordingFailed = recorder.state === "denied" || recorder.state === "error";
  const displayPhase = recording ? "recording" : recordingFailed ? "error" : phase;
  const displayError = recordingFailed ? recorder.error ?? "Recording is unavailable. You can still type." : error;
  const adoptTranscript = () => {
    if (used.current || !current()) return;
    used.current = true;
    if (callbacks.current.onTranscript(transcript.trim()) === true && current()) finish(id);
  };
  return <VoiceAttemptView phase={displayPhase} error={displayError} transcript={transcript} onTranscriptChange={setTranscript} stop={stop} cancel={cancel} onUseTranscript={adoptTranscript} />;
}

function VoiceAttemptView({ phase, error, transcript, onTranscriptChange, stop, cancel, onUseTranscript }: {
  phase: VoicePhase;
  error: string | null;
  transcript: string;
  onTranscriptChange: (value: string) => void;
  stop: () => void;
  cancel: () => void;
  onUseTranscript: () => void;
}) {
  return (
    <div className="px-3 pb-2 shrink-0 space-y-1.5" data-agent-voice onKeyDown={(event) => {
      if (event.key !== "Escape" || event.nativeEvent.isComposing || event.defaultPrevented) return;
      event.preventDefault();
      event.stopPropagation();
      if (phase === "recording") stop();
      else cancel();
    }}>
      <p role="status" aria-live="polite" className="text-xxs text-shadow-1 dark:text-moonlight">
        {voiceStatus[phase]}
      </p>
      {phase === "review" ? (
        <LemonTextarea aria-label="Voice transcript" value={transcript} minRows={2} maxRows={5} onChange={(event) => onTranscriptChange(event.target.value)} />
      ) : null}
      {error ? <p role="alert" className="text-xs text-emperor">{error}</p> : null}
      <div className="flex flex-wrap gap-2">
        {phase === "recording" ? <LemonButton variant="secondary" size="sm" onClick={stop}>Stop recording</LemonButton> : null}
        {phase === "review" ? (
          <LemonButton variant="secondary" size="sm" disabled={!transcript.trim()} title={!transcript.trim() ? "Add words to the transcript first." : undefined} onClick={onUseTranscript}>Use transcript</LemonButton>
        ) : null}
        <LemonButton variant="tertiary" size="sm" onClick={cancel}>Discard voice</LemonButton>
      </div>
      {phase === "review" && !transcript.trim() ? <p className="text-xxs text-shadow-1 dark:text-moonlight">Add words to the transcript first.</p> : null}
    </div>
  );
}
