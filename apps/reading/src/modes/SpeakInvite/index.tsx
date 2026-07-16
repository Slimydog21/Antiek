import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";

import thinkingArt from "../../brand/werner/poses/session/werner_thinking_session_v1.png";
import livingTvArt from "../../brand/werner/poses/session/werner_living_tv_session_v1.webp";
import InterviewVoiceCapture from "../../components/InterviewVoiceCapture";
import { apiFetch } from "../../lib/api";

/**
 * Speak invitee landing (Product Depth SPR-08 M3) — phone-first, voice-first.
 *
 * The whole product thesis: "send a link to his friends and family," and each
 * records their memories on their own time. THIS is the page the invited
 * person lands on. The operator's headline complaint was that today this page
 * makes a non-power-user TYPE — exactly the friction the voice flow exists to
 * remove. So the primary input is now a big tap-to-talk mic; typing is the
 * fallback for people who'd rather write.
 *
 * The invitee is a SOURCE, not an account (real accounts gated on G7), so this
 * route is UNAUTHENTICATED and the URL token is the credential. Recording
 * uploads through the TOKEN-gated voice route (/speak/invite/{token}/voice),
 * which reuses the single voice owner (Whisper → the answer→claim bridge) —
 * no second pipeline. With no model keys, transcription returns an honest
 * "couldn't turn this into words" (no fabricated transcript); the typed
 * fallback always works.
 *
 * Consent is one honest sentence with a safe default — not a checklist wall.
 * Publish is OFF BY DEFAULT and only ever granted by an affirmative opt-IN: the
 * prominent share button grants RECORD ONLY (the friend's words help, privately);
 * a separate, clearly-labelled second button is the only thing that adds publish.
 * Declining outright thanks them and never pushes them into recording.
 *
 * No engineering string is shown.
 */
interface Landing {
  interview_id: string;
  project_id: string;
  project_title: string;
  subject_ref: string | null;
  required_consent_scopes: string[];
  granted_consent_scopes: string[];
  status: string;
  pending_questions: { id: string; text: string }[];
  transcript: { role: string; text: string; ts: string | null; question_id?: string }[];
}

type Phase = "loading" | "invalid" | "error" | "ready";
type Mode = "voice" | "text";

export default function SpeakInvite() {
  const { token } = useParams<{ token: string }>();
  const [landing, setLanding] = useState<Landing | null>(null);
  const [phase, setPhase] = useState<Phase>("loading");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Whether this person has agreed to take part. Consent is two affirmative
  // buttons — share privately (record-only) vs the explicit publish opt-in —
  // never a checklist the invitee must parse. Publish is off by default.
  const [declined, setDeclined] = useState(false);

  const [mode, setMode] = useState<Mode>("voice");
  const [answer, setAnswer] = useState("");
  const [activeQ, setActiveQ] = useState<string | null>(null);
  const [voiceError, setVoiceError] = useState<string | null>(null);
  const [micDenied, setMicDenied] = useState(false);

  const load = useCallback(async () => {
    if (!token) {
      setPhase("invalid");
      return;
    }
    try {
      const r = await apiFetch(`/speak/invite/${encodeURIComponent(token)}`);
      if (r.status === 404) {
        setPhase("invalid");
        return;
      }
      if (!r.ok) {
        setError(`HTTP ${r.status}`);
        setPhase("error");
        return;
      }
      const data: Landing = await r.json();
      setLanding(data);
      setActiveQ((cur) => cur ?? data.pending_questions[0]?.id ?? null);
      setPhase("ready");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
      setPhase("error");
    }
  }, [token]);

  useEffect(() => {
    void load();
  }, [load]);

  const consented =
    landing !== null && landing.granted_consent_scopes.includes("record");

  // Take part. PUBLISH IS OFF BY DEFAULT — it is the one legally-sensitive
  // scope ("did this friend actually agree to be published?"), so it is NEVER
  // in the default grant. The prominent share button calls this with
  // `includePublish=false`, granting RECORD ONLY (plus `attribute` if the
  // invite asks for it — having one's name shown is not the publish-sensitive
  // scope). A friend only ever publishes by actively picking the separate,
  // clearly-labelled publish opt-IN button (`includePublish=true`). The backend
  // supports record-only consent (tests/test_speak_api.py:259-260); the answer
  // gate checks consent (record), not publish, so a record-only friend can
  // still answer in full.
  const takePart = useCallback(async (includePublish: boolean) => {
    if (!token || !landing) return;
    setBusy(true);
    setError(null);
    try {
      // Default path keeps publish out, no matter what the invite asks for.
      // Only the explicit opt-in action adds publish (and only if it was asked).
      const asked = includePublish
        ? landing.required_consent_scopes
        : landing.required_consent_scopes.filter((s) => s !== "publish");
      const scopes = Array.from(new Set(["record", ...asked]));
      const r = await apiFetch(`/speak/invite/${encodeURIComponent(token)}/consent`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ scopes }),
      });
      if (!r.ok) {
        setError("Something went wrong starting — please try again.");
        return;
      }
      await load();
    } finally {
      setBusy(false);
    }
  }, [token, landing, load]);

  const declineInvite = useCallback(async () => {
    if (!token) return;
    setBusy(true);
    try {
      // Best-effort: record the decline. Either way we land on a clean
      // thank-you — never a dead end, never pushed into recording.
      await apiFetch(`/speak/invite/${encodeURIComponent(token)}/decline`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}",
      }).catch(() => {/* a failed decline still resolves to thank-you */});
      setDeclined(true);
    } finally {
      setBusy(false);
    }
  }, [token]);

  const submitText = useCallback(async () => {
    if (!token || !activeQ || !answer.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const r = await apiFetch(`/speak/invite/${encodeURIComponent(token)}/answer`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question_id: activeQ, transcript: answer.trim() }),
      });
      if (!r.ok) {
        setError("Couldn't send your answer — please try again.");
        return;
      }
      setAnswer("");
      setActiveQ(null);
      await load();
    } finally {
      setBusy(false);
    }
  }, [token, activeQ, answer, load]);

  // ── chrome states ──
  if (phase === "loading") {
    return <Centered>Loading your invitation…</Centered>;
  }
  if (phase === "invalid") {
    return (
      <Centered>
        <p className="font-serif text-[16px]">
          This invitation link is invalid or has expired.
        </p>
        <p className="mt-2 font-serif text-[13px] text-ink-mute dark:text-moonlight">
          Ask whoever invited you to send a fresh link.
        </p>
      </Centered>
    );
  }
  if (phase === "error" || !landing) {
    return <Centered>Something went wrong{error ? `: ${error}` : "."}</Centered>;
  }

  if (declined) {
    return (
      <Centered>
        <p className="font-serif text-[18px] text-ink dark:text-bright">Thank you.</p>
        <p className="mt-2 font-serif text-[14px] text-ink-mute dark:text-moonlight">
          No problem at all — nothing's been shared. You can close this page. If
          you change your mind, just open the same link again.
        </p>
      </Centered>
    );
  }

  const pending = landing.pending_questions;
  const active = pending.find((q) => q.id === activeQ) ?? pending[0] ?? null;
  const askingToPublish = landing.required_consent_scopes.includes("publish");

  return (
    <div className="min-h-screen bg-ice-0 px-4 py-10 dark:bg-charcoal-2">
      <div className="mx-auto max-w-md">
        <header className="mb-7 space-y-3 text-center">
          <img
            src={thinkingArt}
            alt=""
            aria-hidden="true"
            data-testid="speak-invite-werner-brand"
            className="mx-auto h-12 w-12 object-contain"
          />
          <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-sun-deep dark:text-sun">
            You've been asked to help
          </p>
          <h1 className="mt-1 font-serif text-2xl text-ink dark:text-bright">
            Remember {landing.subject_ref ?? landing.project_title}
          </h1>
          <img
            src={livingTvArt}
            alt=""
            aria-hidden="true"
            data-testid="speak-invite-living-tv-art"
            className="mx-auto h-14 w-full max-w-sm rounded-md object-cover object-center"
            loading="lazy"
            decoding="async"
          />
          <p className="mt-2 font-serif text-[14px] text-ink-mute dark:text-moonlight">
            Share a memory in your own words. There's no right answer and no
            rush — anything you remember helps.
          </p>
        </header>

        {error && <p className="mb-3 text-center font-serif text-[13px] text-emperor">{error}</p>}

        {!consented ? (
          // ── Warm consent: one honest sentence + a safe (private) default ──
          // The prominent button grants RECORD ONLY — publish is never the
          // default. Public use is a separate, affirmative opt-IN button below,
          // offered only when the invite asks for publish.
          <section className="rounded-md border-2 border-ink bg-ice-0 p-5 text-center shadow-z1 dark:border-charcoal-1 dark:bg-charcoal-1 dark:shadow-z1-night">
            <p className="font-serif text-[15px] text-ink dark:text-bright">
              We'll record and write down what you share, to help tell{" "}
              {landing.subject_ref ? `${landing.subject_ref}'s` : "this"} story.
            </p>
            <p className="mt-2 font-serif text-[13px] text-ink-mute dark:text-moonlight">
              Either way, what you share is kept private unless you choose
              otherwise, and you can ask to have your words removed at any time.
            </p>
            {/* PRIMARY: record-only. Publish is NOT granted here. */}
            <button
              type="button"
              onClick={() => void takePart(false)}
              disabled={busy}
              className="mt-5 w-full rounded-md border-2 border-ink bg-sun px-4 py-3 font-mono text-[14px] font-semibold text-ink shadow-z1 hover:-translate-y-0.5 disabled:opacity-50 dark:shadow-z1-night"
            >
              Yes, I'll share a memory
            </button>
            {askingToPublish && (
              <>
                {/* Publish OPT-IN: an affirmative second choice the friend must
                    actively pick. This is the ONLY action that grants publish —
                    it is a button, never a pre-checked checklist, so "did this
                    friend actually agree to be published?" is always a yes they
                    chose. Grants record + publish. */}
                <button
                  type="button"
                  onClick={() => void takePart(true)}
                  disabled={busy}
                  className="mt-3 block w-full rounded-md border-2 border-ink bg-ice-0 px-4 py-3 font-mono text-[13px] font-semibold text-ink hover:-translate-y-0.5 disabled:opacity-50 dark:border-charcoal-1 dark:bg-charcoal-2 dark:text-bright"
                >
                  Share — and you can use my words in the public story
                </button>
                <p className="mt-2 font-serif text-[12px] text-ink-mute dark:text-moonlight">
                  Either way still helps — sharing privately keeps your words
                  out of the public story unless you choose the second option.
                </p>
              </>
            )}
            <button
              type="button"
              onClick={() => void declineInvite()}
              disabled={busy}
              className="mt-3 font-serif text-[13px] text-ink-mute underline hover:text-ink disabled:opacity-50 dark:text-moonlight dark:hover:text-bright"
            >
              Not right now
            </button>
          </section>
        ) : pending.length === 0 ? (
          // ── Done: warm, resumable, no dead end ──
          <section className="rounded-md border-2 border-ink bg-ice-0 p-5 text-center shadow-z1 dark:border-charcoal-1 dark:bg-charcoal-1 dark:shadow-z1-night">
            <p className="font-serif text-[18px] text-ink dark:text-bright">Thank you.</p>
            <p className="mt-2 font-serif text-[14px] text-ink-mute dark:text-moonlight">
              What you shared is saved. You can close this page and come back to
              the same link anytime to add more — there's no rush.
            </p>
          </section>
        ) : (
          // ── Recording: voice-first, big tap-to-talk; text as fallback ──
          <section className="rounded-md border-2 border-ink bg-ice-0 p-5 shadow-z1 dark:border-charcoal-1 dark:bg-charcoal-1 dark:shadow-z1-night">
            {landing.transcript.filter((t) => t.role === "informant").length > 0 && (
              <details className="mb-4">
                <summary className="cursor-pointer font-mono text-[10px] uppercase tracking-wider text-ink-mute dark:text-moonlight">
                  what you've shared so far (
                  {landing.transcript.filter((t) => t.role === "informant").length})
                </summary>
                <ul className="mt-2 space-y-2">
                  {landing.transcript
                    .filter((t) => t.role === "informant")
                    .map((t, i) => (
                      <li
                        key={i}
                        className="border-l-2 border-rule pl-2 font-serif text-[13px] text-ink dark:border-charcoal-1 dark:text-bright"
                      >
                        {t.text}
                      </li>
                    ))}
                </ul>
              </details>
            )}

            <p className="text-center font-serif text-[18px] leading-snug text-ink dark:text-bright">
              {active?.text}
            </p>

            {mode === "voice" && !micDenied ? (
              <div className="mt-5">
                <PhoneVoiceCapture
                  token={token!}
                  questionId={active?.id ?? ""}
                  onShared={() => {
                    setVoiceError(null);
                    void load();
                  }}
                  onMicDenied={() => {
                    setMicDenied(true);
                    setMode("text");
                  }}
                  onVoiceError={(detail) => setVoiceError(detail)}
                />
                {voiceError && (
                  <p className="mt-3 text-center font-serif text-[13px] text-ink-mute dark:text-moonlight">
                    We couldn't turn that recording into words just now. You can
                    try again, or{" "}
                    <button
                      type="button"
                      className="underline"
                      onClick={() => setMode("text")}
                    >
                      type it instead
                    </button>
                    .
                  </p>
                )}
                <button
                  type="button"
                  onClick={() => setMode("text")}
                  className="mt-4 block w-full text-center font-serif text-[13px] text-ink-mute underline hover:text-ink dark:text-moonlight dark:hover:text-bright"
                >
                  I'd rather type
                </button>
              </div>
            ) : (
              <div className="mt-5">
                {micDenied && (
                  <p className="mb-2 font-serif text-[12px] text-ink-mute dark:text-moonlight">
                    No microphone — no problem. Type your memory below.
                  </p>
                )}
                <textarea
                  value={answer}
                  onChange={(e) => setAnswer(e.target.value)}
                  rows={5}
                  placeholder="Share whatever comes to mind — a story, a detail, a memory."
                  className="w-full rounded border border-rule bg-ice-0 p-3 font-serif text-[15px] text-ink dark:border-charcoal-1 dark:bg-charcoal-2 dark:text-bright"
                />
                <button
                  type="button"
                  onClick={() => void submitText()}
                  disabled={busy || !answer.trim()}
                  className="mt-3 w-full rounded-md border-2 border-ink bg-sun px-4 py-3 font-mono text-[14px] font-semibold text-ink shadow-z1 hover:-translate-y-0.5 disabled:opacity-50 dark:shadow-z1-night"
                >
                  Send this memory
                </button>
                {!micDenied && (
                  <button
                    type="button"
                    onClick={() => setMode("voice")}
                    className="mt-3 block w-full text-center font-serif text-[13px] text-ink-mute underline hover:text-ink dark:text-moonlight dark:hover:text-bright"
                  >
                    or talk instead
                  </button>
                )}
              </div>
            )}

            <p className="mt-5 text-center font-mono text-[10px] text-ink-mute dark:text-moonlight">
              {pending.length} {pending.length === 1 ? "question" : "questions"} waiting · saved as you go
            </p>
          </section>
        )}

        <footer className="mt-6 text-center font-serif text-[11px] text-ink-mute dark:text-moonlight">
          Your words are used only as you agreed. Reach out to whoever invited
          you to have anything removed.
        </footer>
      </div>
    </div>
  );
}

/**
 * The big tap-to-talk mic — phone-first. Wraps the shared capture component
 * (the single voice owner), pointed at the TOKEN-gated invitee voice route.
 * A denied mic permission is an honest fallback (→ type), never a dead end.
 */
function PhoneVoiceCapture({
  token,
  questionId,
  onShared,
  onMicDenied,
  onVoiceError,
}: {
  token: string;
  questionId: string;
  onShared: () => void;
  onMicDenied: () => void;
  onVoiceError: (detail: string) => void;
}) {
  return (
    <div className="rounded-md border border-rule p-4 dark:border-charcoal-1">
      <p className="mb-3 text-center font-serif text-[13px] text-ink-mute dark:text-moonlight">
        Tap to talk — say it however it comes out.
      </p>
      <InterviewVoiceCapture
        buildUploadUrl={(duration) =>
          `/speak/invite/${encodeURIComponent(token)}/voice` +
          `?question_id=${encodeURIComponent(questionId)}&duration_seconds=${duration}`
        }
        onUploaded={() => onShared()}
        onUploadError={(_status, detail) => {
          // A 503 means transcription couldn't run (no model key); surface the
          // engine's reason honestly rather than a fabricated transcript.
          onVoiceError(detail);
        }}
      />
      <p className="mt-2 text-center font-mono text-[10px] text-ink-mute dark:text-moonlight">
        Trouble with the mic?{" "}
        <button type="button" className="underline" onClick={onMicDenied}>
          Type instead
        </button>
      </p>
    </div>
  );
}

function Centered({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-ice-0 px-4 dark:bg-charcoal-2">
      <div className="max-w-md text-center font-serif text-[14px] text-ink dark:text-bright">
        {children}
      </div>
    </div>
  );
}
