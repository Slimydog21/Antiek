import { useEffect, useState } from "react";

import InterviewVoiceCapture from "../../components/InterviewVoiceCapture";
import { apiFetch } from "../../lib/api";

/**
 * InterviewRecording panel (S10 row 10.10).
 *
 * Wraps the existing InterviewVoiceCapture into a panel-friendly
 * container. The operator can dock this left, right, or float it
 * over the main transcript view while running an interview.
 *
 * Consent state is SELF-FETCHED — PanelHost freezes a starter's
 * props at mount time, so we can't trust `consentRecorded` from the
 * parent's freshly-loaded `detail`. We re-fetch on mount + every 5s
 * so the recording widget becomes available the moment the operator
 * records consent in the main view.
 */
type Props = {
  interviewId?: string;
  consentRecorded?: boolean;
};

export default function InterviewRecording({
  interviewId,
  consentRecorded: initialConsent,
}: Props) {
  const [consentRecorded, setConsentRecorded] = useState<boolean>(
    Boolean(initialConsent),
  );

  useEffect(() => {
    if (!interviewId) return;
    let cancelled = false;
    const poll = async () => {
      try {
        const resp = await apiFetch(
          `/interviews/${encodeURIComponent(interviewId)}`,
        );
        if (!resp.ok) return;
        const data = await resp.json();
        if (!cancelled) {
          setConsentRecorded(Boolean(data.consent_recorded));
        }
      } catch {
        // best-effort; the substrate is still the gatekeeper
      }
    };
    void poll();
    const t = setInterval(poll, 5_000);
    return () => {
      cancelled = true;
      clearInterval(t);
    };
  }, [interviewId]);

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
