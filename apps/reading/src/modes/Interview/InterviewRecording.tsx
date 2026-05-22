import InterviewVoiceCapture from "../../components/InterviewVoiceCapture";

/**
 * InterviewRecording panel (S10 row 10.10).
 *
 * Wraps the existing InterviewVoiceCapture into a panel-friendly
 * container. The operator can dock this left, right, or float it
 * over the main transcript view while running an interview.
 *
 * Props are passed-through to the underlying component; the panel
 * is just chrome + the same recording UI.
 */
type Props = {
  interviewId?: string;
  consentRecorded?: boolean;
};

export default function InterviewRecording({
  interviewId,
  consentRecorded,
}: Props) {
  return (
    <div className="h-full overflow-y-auto p-3 bg-ice-0 dark:bg-charcoal-2">
      <h3 className="text-xs font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight mb-2">
        Recording
      </h3>
      {!interviewId ? (
        <p className="text-[12px] font-mono italic text-ink-mute dark:text-moonlight">
          No interview loaded. Open one at /interview/&lt;id&gt; — this
          panel attaches to the currently-active session.
        </p>
      ) : !consentRecorded ? (
        <div className="border-l-edge border-sun bg-sun/10 p-3 text-[12px] text-ink dark:text-bright">
          Consent not yet recorded for this interview. Record consent
          in the main view before capturing audio — the substrate
          rejects turns without it (master-spec §13.3).
        </div>
      ) : (
        <InterviewVoiceCapture
          sessionId={interviewId}
          onUploaded={() => {
            // Best-effort: the main route polls / refreshes on its own
            // cycle. Future improvement: emit a `transcript:refresh`
            // workspace event the InterviewTranscript panel listens for.
          }}
        />
      )}
    </div>
  );
}
