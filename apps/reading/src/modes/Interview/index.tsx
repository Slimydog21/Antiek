import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";

import InterviewVoiceCapture from "../../components/InterviewVoiceCapture";
import { apiFetch } from "../../lib/api";
import { PanelHost } from "../../workspace/PanelHost";

/**
 * Loop 4 interview surface (master-spec §11.5 + integration_autoresearch §B).
 *
 * Three-pane conversation UI:
 *  1. Header — interview metadata + status + consent state
 *  2. Transcript — running interviewer/informant turns
 *  3. Compose — text input + voice capture + must-cover progress
 *
 * The orchestrator (orchestration/interview/orchestrator.py) owns
 * the state machine; this surface is the operator-facing renderer.
 * Per master-spec §13.3: consent recording is binding — the
 * substrate refuses to advance turns without it.
 */

interface InterviewTurn {
  role: "interviewer" | "informant";
  text: string;
  ts: string | null;
}

interface InterviewDetail {
  interview_id: string;
  project_id: string;
  project_title: string;
  topic_description: string | null;
  framing: string | null;
  must_cover: string[];
  status: string;
  consent_recorded: boolean;
  transcript: InterviewTurn[];
}

export default function InterviewMode() {
  const { interviewId } = useParams<{ interviewId: string }>();
  const [detail, setDetail] = useState<InterviewDetail | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [draftInformant, setDraftInformant] = useState<string>("");
  const [draftInterviewer, setDraftInterviewer] = useState<string>("");
  const [submitting, setSubmitting] = useState<boolean>(false);

  const reload = useCallback(async () => {
    if (!interviewId) return;
    setLoading(true);
    setError(null);
    try {
      const resp = await apiFetch(
        `/interviews/${encodeURIComponent(interviewId)}`,
      );
      if (!resp.ok) {
        throw new Error(`GET /interviews failed: HTTP ${resp.status}`);
      }
      setDetail(await resp.json());
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [interviewId]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const postTurn = async (role: "interviewer" | "informant", text: string) => {
    if (!interviewId || !text.trim() || submitting) return;
    setSubmitting(true);
    try {
      const resp = await apiFetch(
        `/interviews/${encodeURIComponent(interviewId)}/turn`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ role, text }),
        },
      );
      if (!resp.ok) {
        throw new Error(`POST turn failed: HTTP ${resp.status}`);
      }
      if (role === "informant") setDraftInformant("");
      if (role === "interviewer") setDraftInterviewer("");
      await reload();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSubmitting(false);
    }
  };

  const completeInterview = async () => {
    if (!interviewId || submitting) return;
    setSubmitting(true);
    try {
      const resp = await apiFetch(
        `/interviews/${encodeURIComponent(interviewId)}/complete`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({}),
        },
      );
      if (!resp.ok) {
        throw new Error(`Complete failed: HTTP ${resp.status}`);
      }
      await reload();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSubmitting(false);
    }
  };

  // S10 row 10.10 — Interview wraps the main compose surface in
  // PanelHost. Three starter panels:
  //   - InterviewRecording  docked-left   (voice capture widget)
  //   - InterviewTranscript docked-right  (read-only transcript)
  //   - InterviewNotes      docked-bottom (operator-private scratchpad)
  // The starters' props are derived from the loaded `detail`; the
  // main slot keeps the existing compose-form + header rendering.
  const starters = interviewId
    ? [
        {
          kind: "InterviewRecording" as const,
          mode: "docked-left" as const,
          title: "Recording",
          id: `interview:${interviewId}:recording`,
          props: {
            interviewId,
            consentRecorded: detail?.consent_recorded ?? false,
          },
        },
        {
          kind: "InterviewTranscript" as const,
          mode: "docked-right" as const,
          title: "Transcript",
          id: `interview:${interviewId}:transcript`,
          props: { interviewId },
        },
        {
          kind: "InterviewNotes" as const,
          mode: "docked-bottom" as const,
          title: "Notes",
          id: `interview:${interviewId}:notes`,
          props: { interviewId },
        },
      ]
    : [];

  return (
    <PanelHost starters={starters}>
      <main className="h-full overflow-y-auto bg-ice-0 dark:bg-charcoal-2">
        <div className="max-w-5xl mx-auto px-8 py-10 space-y-6">
          <header className="space-y-2">
            <h1 className="text-2xl font-serif text-ink dark:text-bright">
              Interview
            </h1>
            <p className="text-sm text-ink-soft dark:text-starlight leading-relaxed">
              Loop 4 informant interview surface. Per master-spec
              §11.5: consent must be recorded before any turn lands;
              the substrate enforces this at the orchestrator level.
            </p>
            <p className="text-xs font-mono text-shadow-1 dark:text-moonlight">
              interview_id = {interviewId ?? "—"}
            </p>
          </header>

          {loading && (
            <p className="text-sm text-shadow-1 dark:text-moonlight italic">Loading interview…</p>
          )}
          {error && (
            <p className="text-sm text-emperor border border-red-200 bg-red-50 px-3 py-2 rounded">
              {error}
            </p>
          )}

          {detail && (
            <>
              <section className="border border-rule dark:border-charcoal-1 rounded-md p-5 space-y-3">
                <div className="flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <h2 className="text-base font-serif text-ink dark:text-bright truncate">
                      {detail.project_title}
                    </h2>
                    {detail.topic_description && (
                      <p className="text-xs text-ink-soft dark:text-starlight truncate">
                        {detail.topic_description}
                      </p>
                    )}
                  </div>
                  <span
                    className={`text-[10px] uppercase tracking-wider font-mono px-2 py-0.5 rounded ${
                      detail.status === "completed"
                        ? "bg-emerald-100 text-emerald-700"
                        : "bg-ice-3 dark:bg-charcoal-1 text-ink-soft dark:text-starlight"
                    }`}
                  >
                    {detail.status}
                  </span>
                </div>
                <p className="text-xs text-shadow-1 dark:text-moonlight font-mono">
                  consent_recorded ={" "}
                  {detail.consent_recorded ? "true" : "false"}
                  {" · "}must_cover = {detail.must_cover.length}
                </p>
              </section>

              <section className="border border-rule dark:border-charcoal-1 rounded-md p-5 space-y-3">
                <h3 className="text-sm font-serif text-ink dark:text-bright">Transcript</h3>
                {detail.transcript.length === 0 ? (
                  <p className="text-xs italic text-shadow-1 dark:text-moonlight">
                    No turns recorded yet.
                  </p>
                ) : (
                  <ul className="space-y-3">
                    {detail.transcript.map((t, idx) => (
                      <li
                        key={idx}
                        className={`p-3 rounded ${
                          t.role === "interviewer"
                            ? "bg-ice-1 dark:bg-charcoal-2 border-l-2 border-glacial-1 dark:border-slate-1"
                            : "bg-emerald-50 border-l-2 border-emerald-600"
                        }`}
                      >
                        <p className="text-[10px] uppercase tracking-wider font-mono text-shadow-1 dark:text-moonlight mb-1">
                          {t.role}
                          {t.ts ? ` · ${t.ts}` : ""}
                        </p>
                        <p className="text-sm text-ink dark:text-bright whitespace-pre-wrap">
                          {t.text}
                        </p>
                      </li>
                    ))}
                  </ul>
                )}
              </section>

              {detail.status !== "completed" && (
                <section className="grid md:grid-cols-2 gap-4">
                  <div className="border border-rule dark:border-charcoal-1 rounded-md p-4 space-y-2">
                    <p className="text-xs font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                      Interviewer turn
                    </p>
                    <textarea
                      value={draftInterviewer}
                      onChange={(e) => setDraftInterviewer(e.target.value)}
                      rows={3}
                      placeholder="What's the next question?"
                      className="w-full text-sm font-serif text-ink dark:text-bright border border-rule dark:border-charcoal-1 rounded p-2 resize-y"
                    />
                    <button
                      type="button"
                      onClick={() =>
                        void postTurn("interviewer", draftInterviewer)
                      }
                      disabled={submitting || !draftInterviewer.trim()}
                      className="w-full px-3 py-1.5 rounded-md bg-ink text-white text-xs font-medium hover:bg-shadow-2 transition-colors disabled:opacity-50"
                    >
                      Record interviewer turn
                    </button>
                  </div>

                  <div className="border border-rule dark:border-charcoal-1 rounded-md p-4 space-y-2">
                    <p className="text-xs font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                      Informant turn
                    </p>
                    <textarea
                      value={draftInformant}
                      onChange={(e) => setDraftInformant(e.target.value)}
                      rows={3}
                      placeholder="Informant's response…"
                      className="w-full text-sm font-serif text-ink dark:text-bright border border-rule dark:border-charcoal-1 rounded p-2 resize-y"
                    />
                    <button
                      type="button"
                      onClick={() =>
                        void postTurn("informant", draftInformant)
                      }
                      disabled={submitting || !draftInformant.trim()}
                      className="w-full px-3 py-1.5 rounded-md bg-emerald-700 text-white text-xs font-medium hover:bg-emerald-600 transition-colors disabled:opacity-50"
                    >
                      Record informant turn
                    </button>
                  </div>
                </section>
              )}

              {detail.status !== "completed" && interviewId && (
                <section className="space-y-3">
                  <InterviewVoiceCapture sessionId={interviewId} />
                  <button
                    type="button"
                    onClick={() => void completeInterview()}
                    disabled={submitting}
                    className="px-3 py-1.5 rounded-md border border-rule dark:border-charcoal-1 text-ink dark:text-bright text-xs font-medium hover:bg-ice-1 dark:bg-charcoal-2 transition-colors disabled:opacity-50"
                  >
                    Mark interview complete
                  </button>
                </section>
              )}
            </>
          )}
        </div>
      </main>
    </PanelHost>
  );
}
