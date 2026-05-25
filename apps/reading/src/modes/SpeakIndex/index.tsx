import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { apiFetch } from "../../lib/api";

/**
 * Speak index — the operator's biography-project surface (specs/speak/).
 *
 * Lists every Speak project and lets the operator create one. Each
 * project links to /speak/:projectId where the console (invites,
 * corroboration, draft, publish) lives. Wires the /speak REST surface
 * (interfaces/research/api/speak_routes.py).
 *
 * Speak is interview-as-acquisition: invite a subject's friends and
 * family, interview them, corroborate across them, author with Write,
 * publish with Read. This page is the entry point.
 */
interface SpeakProjectRow {
  project_id: string;
  title: string;
  subject_ref: string | null;
  subject_status: string;
  publish_intent: string;
  invitation_mode: string;
  interview_count: number;
  created_at: string | null;
}

const SUBJECT_STATUSES = ["unknown", "living", "deceased", "non_identifiable"] as const;
const PUBLISH_INTENTS = ["private_never_published", "will_be_public"] as const;

export default function SpeakIndex() {
  const [projects, setProjects] = useState<SpeakProjectRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [title, setTitle] = useState("");
  const [subjectRef, setSubjectRef] = useState("");
  const [subjectStatus, setSubjectStatus] = useState<(typeof SUBJECT_STATUSES)[number]>("unknown");
  const [publishIntent, setPublishIntent] =
    useState<(typeof PUBLISH_INTENTS)[number]>("private_never_published");
  const [submitting, setSubmitting] = useState(false);

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await apiFetch("/speak/projects");
      if (!resp.ok) {
        setError(`HTTP ${resp.status}`);
        return;
      }
      const data = await resp.json();
      setProjects(Array.isArray(data.projects) ? data.projects : []);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  const create = useCallback(async () => {
    if (!title.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      const resp = await apiFetch("/speak/projects", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: title.trim(),
          subject_ref: subjectRef.trim() || null,
          subject_status: subjectStatus,
          publish_intent: publishIntent,
        }),
      });
      if (!resp.ok) {
        setError(`create failed: HTTP ${resp.status}`);
        return;
      }
      setTitle("");
      setSubjectRef("");
      await reload();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSubmitting(false);
    }
  }, [title, subjectRef, subjectStatus, publishIntent, reload]);

  return (
    <div className="h-full overflow-y-auto p-6 bg-ice-0 dark:bg-charcoal-2 max-w-3xl mx-auto">
      <header className="mb-4">
        <h1 className="text-lg font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
          Speak · biography projects
        </h1>
        <p className="text-[12px] font-serif text-ink-mute dark:text-moonlight mt-1">
          Invite a subject's friends and family, interview them, corroborate across
          them, then author + publish. Invitees are sources, not accounts.
        </p>
      </header>

      <section className="border-2 border-ink rounded p-3 mb-5">
        <h2 className="text-xs font-mono uppercase tracking-wider mb-2 text-shadow-1 dark:text-moonlight">
          New project
        </h2>
        <div className="flex flex-col gap-2">
          <input
            value={title}
            placeholder="Title (e.g. Dad's biography)"
            onChange={(e) => setTitle(e.target.value)}
            className="font-serif text-[14px] px-2 py-1 border border-ink-mute rounded bg-ice-0 dark:bg-charcoal-1 text-ink dark:text-bright"
          />
          <input
            value={subjectRef}
            placeholder="Subject reference (who the biography is about)"
            onChange={(e) => setSubjectRef(e.target.value)}
            className="font-serif text-[14px] px-2 py-1 border border-ink-mute rounded bg-ice-0 dark:bg-charcoal-1 text-ink dark:text-bright"
          />
          <div className="flex gap-2">
            <select
              value={subjectStatus}
              onChange={(e) => setSubjectStatus(e.target.value as (typeof SUBJECT_STATUSES)[number])}
              className="font-mono text-[11px] px-2 py-1 border border-ink-mute rounded bg-ice-0 dark:bg-charcoal-1 text-ink dark:text-bright"
            >
              {SUBJECT_STATUSES.map((s) => (
                <option key={s} value={s}>subject: {s}</option>
              ))}
            </select>
            <select
              value={publishIntent}
              onChange={(e) => setPublishIntent(e.target.value as (typeof PUBLISH_INTENTS)[number])}
              className="font-mono text-[11px] px-2 py-1 border border-ink-mute rounded bg-ice-0 dark:bg-charcoal-1 text-ink dark:text-bright"
            >
              {PUBLISH_INTENTS.map((p) => (
                <option key={p} value={p}>{p.replace(/_/g, " ")}</option>
              ))}
            </select>
            <button
              type="button"
              onClick={() => void create()}
              disabled={submitting || !title.trim()}
              className="font-mono text-[11px] px-3 py-1 border border-ink rounded text-sun-deep dark:text-sun hover:underline disabled:opacity-40"
            >
              create
            </button>
          </div>
          {publishIntent === "will_be_public" && (
            <p className="text-[10px] font-mono text-warning dark:text-sun">
              will-be-public ⇒ invites capture publish-scope consent; public
              publishing is gated on the legal gate (G2/G3).
            </p>
          )}
        </div>
      </section>

      {error && <p className="text-[12px] text-emperor font-mono mb-2">{error}</p>}
      {loading ? (
        <p className="text-[12px] italic text-ink-mute dark:text-moonlight font-serif">Loading…</p>
      ) : projects.length === 0 ? (
        <p className="text-[12px] italic text-ink-mute dark:text-moonlight font-serif">
          No projects yet — create one above.
        </p>
      ) : (
        <ul className="space-y-2">
          {projects.map((p) => (
            <li key={p.project_id}>
              <Link
                to={`/speak/${p.project_id}`}
                className="block border border-ink-mute/40 rounded p-3 hover:border-ink transition-colors"
              >
                <div className="flex items-center justify-between">
                  <span className="font-serif text-[15px] text-ink dark:text-bright">{p.title}</span>
                  <span className="font-mono text-[10px] text-ink-mute dark:text-moonlight">
                    {p.interview_count} invitee{p.interview_count === 1 ? "" : "s"}
                  </span>
                </div>
                <div className="flex gap-2 mt-1">
                  <span className="font-mono text-[9px] uppercase tracking-wider text-sun-deep dark:text-sun">
                    {p.publish_intent.replace(/_/g, " ")}
                  </span>
                  {p.subject_ref && (
                    <span className="font-mono text-[9px] text-ink-mute dark:text-moonlight">
                      subject: {p.subject_ref} ({p.subject_status})
                    </span>
                  )}
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
