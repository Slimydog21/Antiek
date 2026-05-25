import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { apiFetch } from "../../lib/api";
import Invites, { type InviteRow, type InviteStatus } from "./Invites";

/**
 * Speak project console (specs/speak/) — the operator's workspace for
 * one biography project, wired to the /speak REST surface.
 *
 * The operator loop: invite stakeholders, watch their interviews,
 * corroborate across them, draft the biography, and publish per mode.
 * Every gate refusal (legal/consent/G7) surfaces its specific reason —
 * the UI never pretends a blocked action succeeded.
 *
 * Authoring + publishing reuse Write + Read under the hood; this surface
 * drives the Speak-owned orchestration. v1 is single-operator: invitees
 * are sources, not accounts (the public ecosystem is gated on G7).
 */
interface Project {
  project_id: string;
  title: string;
  subject_ref: string | null;
  subject_status: string;
  publish_intent: string;
  invitation_mode: string;
}

interface Economics {
  cell: string;
  inference_margin: string;
  split_applies: boolean;
  creator_carries_cost: boolean;
}

interface LifecycleRow {
  interview_id: string;
  informant_email: string | null;
  informant_handle: string | null;
  status: string;
  link: string | null;
  required_consent_scopes: string[];
}

async function readError(resp: Response): Promise<string> {
  try {
    const body = await resp.json();
    return typeof body.detail === "string" ? body.detail : `HTTP ${resp.status}`;
  } catch {
    return `HTTP ${resp.status}`;
  }
}

export default function Speak() {
  const { projectId } = useParams<{ projectId: string }>();
  const [project, setProject] = useState<Project | null>(null);
  const [economics, setEconomics] = useState<Economics | null>(null);
  const [invites, setInvites] = useState<InviteRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [actionLog, setActionLog] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [draftPublic, setDraftPublic] = useState(false);
  const [draftProse, setDraftProse] = useState<string | null>(null);

  const reload = useCallback(async () => {
    if (!projectId) return;
    setError(null);
    try {
      const [pr, ec, iv] = await Promise.all([
        apiFetch(`/speak/projects/${projectId}`),
        apiFetch(`/speak/projects/${projectId}/economics`),
        apiFetch(`/speak/projects/${projectId}/invites`),
      ]);
      if (pr.ok) setProject(await pr.json());
      else setError(`project: HTTP ${pr.status}`);
      if (ec.ok) setEconomics(await ec.json());
      if (iv.ok) {
        const data = await iv.json();
        const rows: LifecycleRow[] = Array.isArray(data.invites) ? data.invites : [];
        setInvites(rows.map((r) => ({
          interviewId: r.interview_id,
          email: r.informant_email,
          handle: r.informant_handle,
          status: r.status as InviteStatus,
          link: r.link ?? "",
          requiredScopes: (r.required_consent_scopes ?? []) as InviteRow["requiredScopes"],
        })));
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [projectId]);

  useEffect(() => { void reload(); }, [reload]);

  const invite = useCallback(async (email: string) => {
    if (!projectId) return;
    const resp = await apiFetch(`/speak/projects/${projectId}/invites`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ informant_email: email }),
    });
    if (!resp.ok) { setActionError(await readError(resp)); return; }
    await reload();
  }, [projectId, reload]);

  const runAction = useCallback(
    async (label: string, path: string, body?: unknown, ok?: (data: unknown) => string) => {
      if (!projectId) return;
      setActionError(null);
      setActionLog(`${label}…`);
      try {
        const resp = await apiFetch(`/speak/projects/${projectId}${path}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body ?? {}),
        });
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok) {
          setActionLog(null);
          setActionError(`${label} refused: ${typeof data.detail === "string" ? data.detail : `HTTP ${resp.status}`}`);
          return;
        }
        setActionLog(ok ? ok(data) : `${label} ✓`);
        await reload();
      } catch (e: unknown) {
        setActionLog(null);
        setActionError(e instanceof Error ? e.message : String(e));
      }
    },
    [projectId, reload],
  );

  if (!projectId) {
    return <div className="p-6 font-mono text-[12px]">No project selected. <Link to="/speak" className="text-sun-deep underline">← projects</Link></div>;
  }

  return (
    <div className="h-full overflow-y-auto p-6 bg-ice-0 dark:bg-charcoal-2 max-w-3xl mx-auto">
      <Link to="/speak" className="font-mono text-[10px] text-sun-deep dark:text-sun hover:underline">
        ← all projects
      </Link>
      <header className="mt-2 mb-4">
        <h1 className="text-lg font-serif text-ink dark:text-bright">
          {project?.title ?? projectId}
        </h1>
        {project && (
          <p className="text-[11px] font-mono text-ink-mute dark:text-moonlight mt-1">
            {project.publish_intent.replace(/_/g, " ")}
            {project.subject_ref && ` · subject: ${project.subject_ref} (${project.subject_status})`}
          </p>
        )}
        {economics && (
          <p className="text-[10px] font-mono mt-1 text-aurora">
            economics: {economics.cell} · margin {economics.inference_margin} ·
            {economics.split_applies ? " 70% contributor split" : " creator carries cost"}
          </p>
        )}
      </header>

      {error && <p className="text-[12px] text-emperor font-mono mb-2">{error}</p>}

      <section className="mb-5">
        <Invites
          projectTitle={project?.title ?? projectId}
          publishIntent={
            project?.publish_intent === "will_be_public" ? "will_be_public" : "private_never_published"
          }
          invites={invites}
          onInvite={invite}
        />
      </section>

      <section className="border-2 border-ink rounded p-3">
        <h2 className="text-xs font-mono uppercase tracking-wider mb-2 text-shadow-1 dark:text-moonlight">
          Author &amp; publish
        </h2>
        <div className="flex flex-wrap gap-2 items-center">
          <button type="button" onClick={() => void runAction(
            "corroborate", "/corroborate", {},
            (d) => `corroborate ✓ — ${(d as { clusters?: unknown[] }).clusters?.length ?? 0} clusters`,
          )} className="font-mono text-[11px] px-3 py-1 border border-ink rounded text-sun-deep dark:text-sun hover:underline">
            corroborate
          </button>
          <label className="font-mono text-[10px] flex items-center gap-1 text-ink-mute dark:text-moonlight">
            <input type="checkbox" checked={draftPublic} onChange={(e) => setDraftPublic(e.target.checked)} />
            public
          </label>
          <button type="button" onClick={() => void runAction(
            "draft", "/draft", { public: draftPublic },
            (d) => {
              const data = d as { prose_text?: string; excluded_claim_ids?: unknown[] };
              setDraftProse(data.prose_text ?? "");
              return `draft ✓ — ${(data.excluded_claim_ids ?? []).length} excluded`;
            },
          )} className="font-mono text-[11px] px-3 py-1 border border-ink rounded text-sun-deep dark:text-sun hover:underline">
            generate draft
          </button>
          <button type="button" onClick={() => void runAction(
            "publish", "/publish", {},
            (d) => {
              const data = d as { served?: boolean; servability?: string };
              return `publish ✓ — ${data.served ? "served" : "not served"} (${data.servability})`;
            },
          )} className="font-mono text-[11px] px-3 py-1 border border-ink rounded text-sun-deep dark:text-sun hover:underline">
            publish
          </button>
          <button type="button" onClick={() => void runAction(
            "book order", "/book-orders", { book_format: "paperback", page_count: 200 },
            (d) => `book quote ✓ — $${(d as { cost_usd?: string }).cost_usd} (${(d as { payer?: string }).payer})`,
          )} className="font-mono text-[11px] px-3 py-1 border border-ink rounded text-sun-deep dark:text-sun hover:underline">
            quote paperback
          </button>
        </div>
        {actionLog && <p className="mt-2 text-[11px] font-mono text-aurora">{actionLog}</p>}
        {actionError && <p className="mt-2 text-[11px] font-mono text-emperor">{actionError}</p>}
        {draftProse !== null && (
          <pre className="mt-3 p-2 text-[12px] font-serif whitespace-pre-wrap border border-ink-mute/40 rounded bg-ice-0 dark:bg-charcoal-1 text-ink dark:text-bright max-h-64 overflow-y-auto">
            {draftProse || "(empty draft — thin project, no padding)"}
          </pre>
        )}
      </section>
    </div>
  );
}
