import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import SessionBrandChrome from "../../brand/SessionBrandChrome";
import { apiFetch } from "../../lib/api";

/**
 * Interview index — operator-facing project + invite surface
 * (master-spec §11.5).
 *
 * Lists every interview project, lets the operator create a new one,
 * and invites informants to a project. Each invited interview links
 * to /interview/:id where the Loop 4 conversation surface lives.
 *
 * The substrate has all the endpoints already — POST/GET
 * /interview-projects, POST /interviews (invite), GET /interviews
 * (per project). This UI just wires them together.
 */

interface InterviewProject {
  project_id: string;
  title: string;
  topic_description: string | null;
  deliverable_id: string | null;
  must_cover: string[];
  framing: string | null;
  interview_count: number;
  completed_count: number;
  created_at: string | null;
}

interface InterviewSummaryRow {
  interview_id: string;
  project_id: string;
  informant_handle: string | null;
  informant_email: string | null;
  status: string;
  turn_count: number;
}

export default function InterviewIndex() {
  const [projects, setProjects] = useState<InterviewProject[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Project-create draft state
  const [draftTitle, setDraftTitle] = useState<string>("");
  const [draftTopic, setDraftTopic] = useState<string>("");
  const [draftMustCover, setDraftMustCover] = useState<string>("");
  const [draftFraming, setDraftFraming] = useState<string>("");
  const [submitting, setSubmitting] = useState<boolean>(false);

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await apiFetch("/interview-projects");
      if (!resp.ok) {
        throw new Error(
          `GET /interview-projects failed: HTTP ${resp.status}`,
        );
      }
      const data = await resp.json();
      setProjects(Array.isArray(data) ? data : []);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  const createProject = async () => {
    if (!draftTitle.trim() || submitting) return;
    setSubmitting(true);
    try {
      const mustCover = draftMustCover
        .split("\n")
        .map((s) => s.trim())
        .filter(Boolean);
      const resp = await apiFetch("/interview-projects", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: draftTitle.trim(),
          topic_description: draftTopic.trim() || null,
          must_cover: mustCover,
          framing: draftFraming.trim() || null,
        }),
      });
      if (!resp.ok) {
        throw new Error(`POST /interview-projects: HTTP ${resp.status}`);
      }
      setDraftTitle("");
      setDraftTopic("");
      setDraftMustCover("");
      setDraftFraming("");
      await reload();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="flex flex-col h-screen">
      <main className="flex-1 overflow-y-auto bg-ice-0 dark:bg-charcoal-2">
        <div className="max-w-5xl mx-auto px-8 py-10 space-y-8">
          <SessionBrandChrome
            testIdPrefix="interviews-home"
            title="Interviews"
          >
            <p className="text-sm text-ink-soft dark:text-starlight leading-relaxed">
              Operator-facing index of interview projects + invited
              informants. Per master-spec §11.5: every Loop 4 interview
              is scoped to a project that defines the must-cover
              questions and framing.
            </p>
          </SessionBrandChrome>

          {error && (
            <p className="text-sm text-emperor border border-red-200 bg-red-50 px-3 py-2 rounded">
              {error}
            </p>
          )}

          <section className="border border-rule dark:border-charcoal-1 rounded-md p-5 space-y-3">
            <h2 className="text-base font-serif text-ink dark:text-bright">
              New project
            </h2>
            <div className="space-y-2">
              <input
                type="text"
                value={draftTitle}
                onChange={(e) => setDraftTitle(e.target.value)}
                placeholder="Title (e.g. 'Karen on the 2008 housing crash')"
                className="w-full text-sm font-serif text-ink dark:text-bright border border-rule dark:border-charcoal-1 rounded p-2"
              />
              <textarea
                value={draftTopic}
                onChange={(e) => setDraftTopic(e.target.value)}
                rows={2}
                placeholder="Topic description"
                className="w-full text-sm font-serif text-ink dark:text-bright border border-rule dark:border-charcoal-1 rounded p-2 resize-y"
              />
              <textarea
                value={draftMustCover}
                onChange={(e) => setDraftMustCover(e.target.value)}
                rows={3}
                placeholder="Must-cover questions (one per line)"
                className="w-full text-xs font-mono text-ink dark:text-bright border border-rule dark:border-charcoal-1 rounded p-2 resize-y"
              />
              <textarea
                value={draftFraming}
                onChange={(e) => setDraftFraming(e.target.value)}
                rows={2}
                placeholder="Framing — what's the point of this project?"
                className="w-full text-sm font-serif text-ink dark:text-bright border border-rule dark:border-charcoal-1 rounded p-2 resize-y"
              />
              <button
                type="button"
                onClick={() => void createProject()}
                disabled={submitting || !draftTitle.trim()}
                className="px-3 py-1.5 rounded-md bg-ink text-white text-xs font-medium hover:bg-shadow-2 transition-colors disabled:opacity-50"
              >
                Create project
              </button>
            </div>
          </section>

          {loading && (
            <p className="text-sm text-shadow-1 dark:text-moonlight italic">
              Loading projects…
            </p>
          )}

          {!loading && projects.length === 0 && (
            <p className="text-sm text-shadow-1 dark:text-moonlight italic">
              No projects yet. Create one above.
            </p>
          )}

          <section className="space-y-3">
            {projects.map((p) => (
              <ProjectRow
                key={p.project_id}
                project={p}
                onChange={reload}
                onError={setError}
              />
            ))}
          </section>
        </div>
      </main>
    </div>
  );
}

function ProjectRow({
  project,
  onChange,
  onError,
}: {
  project: InterviewProject;
  onChange: () => Promise<void>;
  onError: (err: string) => void;
}) {
  const [interviews, setInterviews] = useState<InterviewSummaryRow[]>([]);
  const [expanded, setExpanded] = useState<boolean>(false);
  const [inviteHandle, setInviteHandle] = useState<string>("");
  const [inviteEmail, setInviteEmail] = useState<string>("");
  const [submitting, setSubmitting] = useState<boolean>(false);

  const loadInterviews = useCallback(async () => {
    try {
      const resp = await apiFetch(
        `/interview-projects/${encodeURIComponent(project.project_id)}/interviews`,
      );
      if (!resp.ok) return;
      const data = await resp.json();
      setInterviews(Array.isArray(data) ? data : []);
    } catch {
      // Best-effort; the project row still renders without interviews.
    }
  }, [project.project_id]);

  useEffect(() => {
    if (expanded) void loadInterviews();
  }, [expanded, loadInterviews]);

  const invite = async () => {
    if (submitting) return;
    setSubmitting(true);
    try {
      const resp = await apiFetch("/interviews", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          project_id: project.project_id,
          informant_handle: inviteHandle.trim() || null,
          informant_email: inviteEmail.trim() || null,
        }),
      });
      if (!resp.ok) {
        throw new Error(`POST /interviews: HTTP ${resp.status}`);
      }
      setInviteHandle("");
      setInviteEmail("");
      await loadInterviews();
      await onChange();
    } catch (e: unknown) {
      onError(e instanceof Error ? e.message : String(e));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <article className="border border-rule dark:border-charcoal-1 rounded-md p-4 space-y-2">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="w-full text-left flex items-baseline justify-between gap-3"
      >
        <div className="min-w-0">
          <h3 className="text-sm font-serif text-ink dark:text-bright truncate">
            {project.title}
          </h3>
          {project.topic_description && (
            <p className="text-xs text-ink-soft dark:text-starlight truncate">
              {project.topic_description}
            </p>
          )}
        </div>
        <span className="text-[10px] uppercase tracking-wider font-mono text-shadow-1 dark:text-moonlight shrink-0">
          {project.completed_count}/{project.interview_count} done
        </span>
      </button>

      {expanded && (
        <div className="pt-2 space-y-3 border-t border-rule dark:border-charcoal-1">
          {project.must_cover.length > 0 && (
            <div className="space-y-1">
              <p className="text-[10px] font-mono uppercase text-shadow-1 dark:text-moonlight">
                Must-cover
              </p>
              <ul className="text-xs text-ink dark:text-bright list-disc pl-5 space-y-0.5">
                {project.must_cover.map((q, i) => (
                  <li key={i}>{q}</li>
                ))}
              </ul>
            </div>
          )}

          <div className="space-y-1">
            <p className="text-[10px] font-mono uppercase text-shadow-1 dark:text-moonlight">
              Invited informants
            </p>
            {interviews.length === 0 ? (
              <p className="text-xs italic text-shadow-1 dark:text-moonlight">
                No interviews invited yet.
              </p>
            ) : (
              <ul className="divide-y divide-rule dark:divide-charcoal-1">
                {interviews.map((i) => (
                  <li
                    key={i.interview_id}
                    className="py-1 flex items-center justify-between gap-2"
                  >
                    <Link
                      to={`/interview/${i.interview_id}`}
                      className="text-xs font-mono text-ink dark:text-bright hover:underline truncate"
                    >
                      {i.informant_handle ||
                        i.informant_email ||
                        i.interview_id}
                    </Link>
                    <span className="text-[10px] uppercase tracking-wider font-mono text-shadow-1 dark:text-moonlight shrink-0">
                      {i.status} · {i.turn_count} turns
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="space-y-2 pt-2 border-t border-rule dark:border-charcoal-1">
            <p className="text-[10px] font-mono uppercase text-shadow-1 dark:text-moonlight">
              Invite informant
            </p>
            <div className="grid grid-cols-2 gap-2">
              <input
                type="text"
                value={inviteHandle}
                onChange={(e) => setInviteHandle(e.target.value)}
                placeholder="Handle (optional)"
                className="text-xs font-mono text-ink dark:text-bright border border-rule dark:border-charcoal-1 rounded p-1.5"
              />
              <input
                type="email"
                value={inviteEmail}
                onChange={(e) => setInviteEmail(e.target.value)}
                placeholder="Email (optional)"
                className="text-xs font-mono text-ink dark:text-bright border border-rule dark:border-charcoal-1 rounded p-1.5"
              />
            </div>
            <button
              type="button"
              onClick={() => void invite()}
              disabled={submitting}
              className="px-3 py-1 rounded-md bg-emerald-700 text-white text-xs font-medium hover:bg-emerald-600 transition-colors disabled:opacity-50"
            >
              Invite
            </button>
          </div>
        </div>
      )}
    </article>
  );
}
