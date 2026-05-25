import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";

import { apiFetch } from "../../lib/api";
import VoiceNoteRecorder from "./VoiceNoteRecorder";

/**
 * Speak invitee landing (specs/speak/) — the friends-and-family page.
 *
 * The whole product thesis: "send a link to his friends and family,"
 * and each records their memories on their own time. THIS is the page
 * the invited person lands on. They are a SOURCE, not an operator
 * account (real accounts are gated on G7), so this route is
 * UNAUTHENTICATED and the URL token is the credential — every call goes
 * to the token-gated /speak/invite/{token} surface, which verifies the
 * token server-side.
 *
 * Flow: resolve token → scoped consent → answer the questions (async,
 * resumable) → done. Consent is honest + scoped: 'record' is required
 * to take part; 'attribute' (be named) and 'publish' (appear in a
 * public biography) are optional, and declining publish simply means
 * those words won't appear in a public version — never silently kept.
 *
 * Answers are text-first: what you type IS the transcript that gets
 * distilled (SPR-02's "distill from the corrected text, not the raw
 * one" — here you author it directly). Device voice-typing works in the
 * box; a full record→auto-transcribe→correct loop for invitees needs
 * the /voice upload path token-gated too, a documented next step.
 */
interface Landing {
  interview_id: string;
  project_id: string;
  project_title: string;
  subject_ref: string | null;
  subject_status: string | null;
  required_consent_scopes: string[];
  granted_consent_scopes: string[];
  status: string;
  pending_questions: { id: string; text: string }[];
  transcript: { role: string; text: string; ts: string | null; question_id?: string }[];
}

type Phase = "loading" | "invalid" | "error" | "ready";

const SCOPE_COPY: Record<string, string> = {
  record:
    "Record and transcribe what I share, to help build this biography. (Required to take part.)",
  attribute: "It's okay to attribute my contributions to me by name.",
  publish:
    "It's okay for my contributions to appear in a publicly-published biography.",
};

export default function SpeakInvite() {
  const { token } = useParams<{ token: string }>();
  const [landing, setLanding] = useState<Landing | null>(null);
  const [phase, setPhase] = useState<Phase>("loading");
  const [error, setError] = useState<string | null>(null);
  const [agreed, setAgreed] = useState<Record<string, boolean>>({});
  const [answer, setAnswer] = useState("");
  const [activeQ, setActiveQ] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

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
      // Default-check 'record' (required); leave attribute/publish opt-in.
      setAgreed((cur) =>
        Object.keys(cur).length ? cur : { record: true },
      );
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
    landing !== null &&
    landing.required_consent_scopes.length > 0 &&
    landing.granted_consent_scopes.includes("record") &&
    // 'record' is the gate to participate; required publish/attribute are
    // encouraged but optional — having granted record is enough to begin.
    true;

  const grantConsent = useCallback(async () => {
    if (!token || !landing) return;
    if (!agreed.record) {
      setError("Recording consent is required to take part.");
      return;
    }
    const scopes = landing.required_consent_scopes.filter((s) => agreed[s]);
    if (!scopes.includes("record")) scopes.push("record");
    setBusy(true);
    setError(null);
    try {
      const r = await apiFetch(`/speak/invite/${encodeURIComponent(token)}/consent`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ scopes }),
      });
      if (!r.ok) {
        setError(`Could not record consent: HTTP ${r.status}`);
        return;
      }
      await load();
    } finally {
      setBusy(false);
    }
  }, [token, landing, agreed, load]);

  const submitAnswer = useCallback(async () => {
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
        setError(`Could not send your answer: HTTP ${r.status}`);
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
        <p className="font-serif text-[15px]">This invitation link is invalid or has expired.</p>
        <p className="font-mono text-[11px] text-ink-mute dark:text-moonlight mt-2">
          Ask whoever invited you to send a fresh link.
        </p>
      </Centered>
    );
  }
  if (phase === "error" || !landing) {
    return <Centered>Something went wrong{error ? `: ${error}` : "."}</Centered>;
  }

  const pending = landing.pending_questions;
  const active = pending.find((q) => q.id === activeQ) ?? pending[0] ?? null;

  return (
    <div className="min-h-screen bg-ice-0 dark:bg-charcoal-2 px-4 py-10">
      <div className="max-w-xl mx-auto">
        <header className="mb-6">
          <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-sun-deep dark:text-sun">
            You've been invited to contribute
          </p>
          <h1 className="font-serif text-2xl text-ink dark:text-bright mt-1">
            {landing.project_title}
          </h1>
          {landing.subject_ref && (
            <p className="font-serif text-[13px] text-ink-mute dark:text-moonlight mt-1">
              Your memories will help tell {landing.subject_ref}'s story.
            </p>
          )}
        </header>

        {error && <p className="text-[12px] text-emperor font-mono mb-3">{error}</p>}

        {!consented ? (
          <section className="border-2 border-ink rounded p-4">
            <h2 className="font-serif text-[16px] text-ink dark:text-bright mb-2">
              Before we begin — what are you comfortable with?
            </h2>
            <p className="font-serif text-[13px] text-ink-mute dark:text-moonlight mb-3">
              You're in control. Pick what you agree to; you can ask for your
              words to be removed at any time.
            </p>
            <div className="space-y-2">
              {landing.required_consent_scopes.map((scope) => (
                <label key={scope} className="flex items-start gap-2 text-[13px] font-serif text-ink dark:text-bright">
                  <input
                    type="checkbox"
                    checked={Boolean(agreed[scope])}
                    onChange={(e) => setAgreed((c) => ({ ...c, [scope]: e.target.checked }))}
                    className="mt-1"
                  />
                  <span>{SCOPE_COPY[scope] ?? scope}</span>
                </label>
              ))}
            </div>
            {landing.required_consent_scopes.includes("publish") && !agreed.publish && (
              <p className="font-mono text-[10px] text-warning dark:text-sun mt-2">
                If you don't agree to publish, your contributions still help —
                they just won't appear in a public version.
              </p>
            )}
            <button
              type="button"
              onClick={() => void grantConsent()}
              disabled={busy || !agreed.record}
              className="mt-4 font-mono text-[12px] px-4 py-1.5 border-2 border-ink rounded bg-ink text-white hover:bg-shadow-2 disabled:opacity-40"
            >
              agree &amp; continue
            </button>
          </section>
        ) : pending.length === 0 ? (
          <section className="border-2 border-ink rounded p-4">
            <h2 className="font-serif text-[16px] text-ink dark:text-bright">Thank you.</h2>
            <p className="font-serif text-[13px] text-ink-mute dark:text-moonlight mt-2">
              Your contributions are saved. You can close this page and come back
              to the same link anytime to add more — there's no rush.
            </p>
          </section>
        ) : (
          <section className="border-2 border-ink rounded p-4">
            {landing.transcript.length > 0 && (
              <details className="mb-3">
                <summary className="font-mono text-[10px] uppercase tracking-wider text-ink-mute dark:text-moonlight cursor-pointer">
                  what you've shared so far ({landing.transcript.filter((t) => t.role === "informant").length})
                </summary>
                <ul className="mt-2 space-y-2">
                  {landing.transcript.filter((t) => t.role === "informant").map((t, i) => (
                    <li key={i} className="font-serif text-[13px] text-ink dark:text-bright border-l-2 border-ink-mute/40 pl-2">
                      {t.text}
                    </li>
                  ))}
                </ul>
              </details>
            )}
            <p className="font-mono text-[10px] uppercase tracking-wider text-sun-deep dark:text-sun">
              A question for you
            </p>
            <p className="font-serif text-[16px] text-ink dark:text-bright mt-1 mb-3">
              {active?.text}
            </p>
            <VoiceNoteRecorder token={token ?? ""} onTranscript={(t) => setAnswer(t)} />
            <textarea
              value={answer}
              onChange={(e) => setAnswer(e.target.value)}
              rows={5}
              placeholder="Record above, or type — a story, a detail, a memory. Whatever you send is what gets used, so edit it until it's right."
              className="w-full font-serif text-[14px] p-2 border border-ink-mute rounded bg-ice-0 dark:bg-charcoal-1 text-ink dark:text-bright"
            />
            <div className="flex items-center gap-3 mt-2">
              <button
                type="button"
                onClick={() => void submitAnswer()}
                disabled={busy || !answer.trim()}
                className="font-mono text-[12px] px-4 py-1.5 border-2 border-ink rounded bg-ink text-white hover:bg-shadow-2 disabled:opacity-40"
              >
                send
              </button>
              <span className="font-mono text-[10px] text-ink-mute dark:text-moonlight">
                {pending.length} question{pending.length === 1 ? "" : "s"} waiting · saved as you go
              </span>
            </div>
          </section>
        )}

        <footer className="mt-6 font-mono text-[9px] text-ink-mute dark:text-moonlight">
          Your contributions are used only as you agreed above. Reach out to
          whoever invited you to have anything removed.
        </footer>
      </div>
    </div>
  );
}

function Centered({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen flex items-center justify-center bg-ice-0 dark:bg-charcoal-2 px-4">
      <div className="max-w-md text-center text-ink dark:text-bright font-serif text-[14px]">
        {children}
      </div>
    </div>
  );
}
