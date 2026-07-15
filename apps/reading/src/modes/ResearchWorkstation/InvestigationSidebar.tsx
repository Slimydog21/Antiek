import { useCallback, useRef, useState } from "react";
import { NavLink, useNavigate, useParams } from "react-router-dom";

import { useInvestigationList } from "../../hooks/useInvestigationList";
import { useInvestigationTree } from "../../hooks/useInvestigationTree";
import type { TreeNode } from "../../hooks/useInvestigationTree";
import {
  API_BASE,
  composeResearchArtifacts,
  composeResearchArtifactsWithETag,
  createCompositionDraft,
  launchComposition,
} from "../../lib/api";
import type { InvestigationSummary } from "../../lib/api";
import TwinNotesPanel from "./TwinNotesPanel";

/**
 * Left sidebar showing past investigations as a tree. Each node carries
 * its question (truncated), status badge, and total cost. Click any
 * node to navigate to /inv/<id>.
 *
 * The tree is built from substrate-side parent_investigation_id fields
 * (canonical) with localStorage as a defensive secondary source — see
 * useInvestigationTree.
 */
export default function InvestigationSidebar() {
  const { investigations, loading, error, refetch } = useInvestigationList();
  const tree = useInvestigationTree(investigations);
  const params = useParams<{ investigationId?: string }>();
  const activeId = params.investigationId ?? null;
  const navigate = useNavigate();
  const [selecting, setSelecting] = useState(false);
  const [selected, setSelected] = useState<string[]>([]);
  const [composeError, setComposeError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [draftRequest, setDraftRequest] = useState<{
    compositionId: string;
    idempotencyKey: string;
    title: string;
  } | null>(null);

  const [composeMode, setComposeMode] = useState(false);
  const [composeEtag, setComposeEtag] = useState<string | null>(null);
  const [composeCompositionId, setComposeCompositionId] = useState<string | null>(null);
  const [followUp, setFollowUp] = useState("");
  const [launchPending, setLaunchPending] = useState(false);
  const [launchError, setLaunchError] = useState<string | null>(null);
  const selectedRef = useRef(selected);
  selectedRef.current = selected;
  const selectedAtLaunchRef = useRef<string[]>([]);
  const launchKeyRef = useRef<string | null>(null);
  const composeGeneration = useRef(0);
  const composeInFlight = useRef(false);

  const toggle = (id: string) => {
    if (composeMode || pending || launchPending) return;
    setComposeError(null);
    setLaunchError(null);
    setDraftRequest(null);
    setSelected((current) => current.includes(id) ? current.filter((item) => item !== id) : [...current, id]);
  };

  const enterCompose = useCallback(async () => {
    if (composeInFlight.current) return;
    composeInFlight.current = true;
    const generation = ++composeGeneration.current;
    const exactSelection = [...selected];
    setPending(true);
    setComposeError(null);
    setLaunchError(null);
    try {
      const result = await composeResearchArtifactsWithETag(selected);
      if (generation !== composeGeneration.current
          || JSON.stringify(selectedRef.current) !== JSON.stringify(exactSelection)) return;
      setComposeEtag(result.etag);
      setComposeCompositionId(result.composition.composition_id);
      setComposeMode(true);
    } catch (cause) {
      if (generation !== composeGeneration.current) return;
      setComposeError(cause instanceof Error ? cause.message : "Could not compose these investigations");
    } finally {
      if (generation === composeGeneration.current) {
        composeInFlight.current = false;
        setPending(false);
      }
    }
  }, [selected]);

  const exitCompose = useCallback(() => {
    composeGeneration.current += 1;
    composeInFlight.current = false;
    setComposeMode(false);
    setComposeEtag(null);
    setComposeCompositionId(null);
    setFollowUp("");
    setLaunchError(null);
    launchKeyRef.current = null;
  }, []);

  const confirmLaunch = useCallback(async () => {
    const question = followUp.trim();
    if (!composeEtag || !composeCompositionId || selected.length < 2 || question.length < 3) return;
    selectedAtLaunchRef.current = [...selected];
    setLaunchPending(true);
    setLaunchError(null);
    try {
      if (!launchKeyRef.current) {
        launchKeyRef.current = crypto.randomUUID();
      }
      const result = await launchComposition(
        composeCompositionId,
        { question },
        composeEtag,
        launchKeyRef.current,
      );
      if (
        JSON.stringify(selectedRef.current) !==
        JSON.stringify(selectedAtLaunchRef.current)
      )
        return;
      navigate(`/inv/${result.investigation_id}`);
    } catch (cause) {
      setLaunchError(cause instanceof Error ? cause.message : "Could not launch research");
    } finally {
      setLaunchPending(false);
    }
  }, [composeEtag, composeCompositionId, selected, investigations, followUp, navigate]);
  const createDraft = async () => {
    const preview = window.open("", "_blank");
    if (preview) preview.opener = null;
    setPending(true);
    setComposeError(null);
    try {
      let exactRequest = draftRequest;
      if (!exactRequest) {
        const composition = await composeResearchArtifacts(selected);
        const first = selected[0];
        const firstQuestion = investigations.find((item) => item.investigation_id === first)?.question;
        exactRequest = {
          compositionId: composition.composition_id,
          idempotencyKey: crypto.randomUUID(),
          title: firstQuestion ? `Analysis: ${firstQuestion}` : "Research analysis",
        };
        setDraftRequest(exactRequest);
      }
      const draft = await createCompositionDraft({
        composition_id: exactRequest.compositionId,
        idempotency_key: exactRequest.idempotencyKey,
        title: exactRequest.title,
      });
      if (preview) {
        preview.location.replace(new URL(`/write/${draft.deliverable_id}`, window.location.origin).toString());
      } else {
        setComposeError("Allow pop-ups to open the review draft");
      }
    } catch (cause) {
      preview?.close();
      setComposeError(cause instanceof Error ? cause.message : "Could not create the review draft");
    } finally {
      setPending(false);
    }
  };
  const compose = async () => {
    const preview = window.open("", "_blank");
    if (preview) preview.opener = null;
    setPending(true);
    setComposeError(null);
    try {
      const result = await composeResearchArtifacts(selected);
      if (preview) {
        preview.location.replace(
          new URL(result.url, API_BASE || window.location.origin).toString(),
        );
      } else {
        setComposeError("Allow pop-ups to open the composed HTML review");
      }
    } catch (cause) {
      preview?.close();
      setComposeError(cause instanceof Error ? cause.message : "Could not compose these investigations");
    } finally {
      setPending(false);
    }
  };

  return (
    <div className="p-3 text-xs text-ink dark:text-bright">
      <div className="flex items-center justify-between mb-3">
        <div className="font-mono text-shadow-1 dark:text-moonlight font-semibold uppercase tracking-wider">
          Investigations
        </div>
        <button
          onClick={() => { setSelecting((value) => !value); setComposeError(null); exitCompose(); }}
          disabled={pending || launchPending}
          aria-pressed={selecting}
          className="text-ink-mute dark:text-moonlight hover:text-ink dark:hover:text-bright transition-colors mr-2"
        >{selecting ? "Done" : "Select"}</button>
        <button
          onClick={refetch}
          className="text-ink-mute dark:text-moonlight hover:text-ink dark:hover:text-bright transition-colors"
          aria-label="Refresh"
        >
          ⟳
        </button>
      </div>
      {selecting && (
        <div className="mb-3 border border-ink-mute/30 rounded p-2" aria-label="Composition selection">
          {composeMode ? (
            <div>
              <div className="font-mono text-[10px] mb-2">Collective research</div>
              <div className="font-mono text-[10px] mb-1">Selected investigations (in order):</div>
              <ol className="list-decimal ml-4 mb-2">
                {selected.map((id) => {
                  const q = investigations.find((item) => item.investigation_id === id)?.question;
                  return <li key={id}>{q ?? id}</li>;
                })}
              </ol>
              <label htmlFor="compose-follow-up" className="font-mono text-[10px] mb-1 block">Follow-up question</label>
              <textarea
                id="compose-follow-up"
                value={followUp}
                onChange={(e) => {
                  setFollowUp(e.target.value);
                  launchKeyRef.current = null;
                }}
                placeholder="What should this combined research investigate next?"
                disabled={launchPending}
                rows={3}
                className="w-full border border-ink-mute/30 rounded p-1 text-[11px] font-serif resize-none bg-transparent mb-2"
              />
              <div className="flex flex-wrap gap-1">
                <button
                  onClick={confirmLaunch}
                  disabled={launchPending || selected.length < 2 || selected.length > 8 || followUp.trim().length < 3}
                  className="bg-sun text-ink px-2 py-1 rounded disabled:opacity-40"
                >
                  {launchPending ? "Launching…" : "Research together"}
                </button>
                <button
                  onClick={exitCompose}
                  disabled={launchPending}
                  className="border border-ink-mute/40 px-2 py-1 rounded disabled:opacity-40"
                >
                  Back
                </button>
              </div>
              {launchError && <div role="alert" className="text-emperor font-mono text-[10px] mt-2">{launchError}</div>}
            </div>
          ) : (
            <>
              <div className="font-mono text-[10px] mb-1" aria-live="polite">{selected.length}/20 selected</div>
              {selected.length > 0 && <ol className="list-decimal ml-4 mb-2">{selected.map((id) => <li key={id}>{id}</li>)}</ol>}
              <div className="flex flex-wrap gap-1">
                <button onClick={createDraft} disabled={pending || selected.length < 2 || selected.length > 20}
                  className="bg-sun text-ink px-2 py-1 rounded disabled:opacity-40">
                  {pending ? "Working…" : "Create review draft"}
                </button>
                <button onClick={compose} disabled={pending || selected.length < 2 || selected.length > 20}
                  className="border border-ink-mute/40 px-2 py-1 rounded disabled:opacity-40">
                  Open HTML
                </button>
                <button onClick={enterCompose} disabled={pending || selected.length < 2 || selected.length > 8}
                  className="border border-ink-mute/40 px-2 py-1 rounded disabled:opacity-40">
                  {pending ? "Composing…" : "Research together"}
                </button>
              </div>
              {composeError && <div role="alert" className="text-emperor font-mono text-[10px] mt-2">{composeError}</div>}
            </>
          )}
        </div>
      )}
      {loading && investigations.length === 0 && (
        <div className="text-ink-mute dark:text-moonlight italic font-mono">Loading…</div>
      )}
      {error && (
        <div className="text-emperor font-mono text-[10px]">{error}</div>
      )}
      {!loading && investigations.length === 0 && !error && (
        <div className="text-ink-mute dark:text-moonlight italic font-serif">
          No investigations yet. Ask a question to start.
        </div>
      )}
      <ul className="space-y-1">
        {tree.map((node) => (
          <TreeRow key={node.investigationId} node={node} depth={0} activeId={activeId}
            selecting={selecting} selected={selected} onToggle={toggle} pending={composeMode || pending || launchPending} />
        ))}
      </ul>
      <TwinNotesPanel />
    </div>
  );
}

function TreeRow({
  node,
  depth,
  activeId,
  selecting, selected, onToggle, pending,
}: {
  node: TreeNode;
  depth: number;
  activeId: string | null;
  selecting: boolean;
  selected: string[];
  onToggle: (id: string) => void;
  pending: boolean;
}) {
  const [expanded, setExpanded] = useState(true);
  const summary = node.summary;
  const isActive = activeId === node.investigationId;
  return (
    <li>
      <div className="flex items-start gap-1.5">
        {selecting && <input type="checkbox" aria-label={`Select ${node.investigationId}`}
          checked={selected.includes(node.investigationId)}
          disabled={pending || summary?.artifact_composable !== true || (!selected.includes(node.investigationId) && selected.length >= 20)}
          aria-describedby={!summary?.artifact_composable ? `compose-reason-${node.investigationId}` : undefined}
          onChange={() => onToggle(node.investigationId)} />}
        {selecting && !summary?.artifact_composable && (
          <span id={`compose-reason-${node.investigationId}`} className="sr-only">
            Only completed research investigations can be composed
          </span>
        )}
        {node.children.length > 0 ? (
          <button
            onClick={() => setExpanded((v) => !v)}
            className="text-ink-mute dark:text-moonlight hover:text-ink dark:text-bright transition-colors w-3 text-center text-[10px] mt-1 shrink-0"
            aria-label={expanded ? "Collapse" : "Expand"}
          >
            {expanded ? "▾" : "▸"}
          </button>
        ) : (
          <span className="w-3 shrink-0" />
        )}
        <NavLink
          to={`/inv/${node.investigationId}`}
          className={`flex-1 min-w-0 py-1 px-1.5 rounded transition-colors relative ${
            isActive
              ? "bg-sun text-ink"
              : "hover:bg-sun/20 dark:hover:bg-sun/15 text-ink dark:text-bright"
          }`}
          style={{ marginLeft: depth * 8 }}
        >
          {isActive && (
            <span aria-hidden="true" className="absolute left-0 top-1 bottom-1 w-0.5 bg-ink" />
          )}
          <div className="flex items-start gap-1.5">
            <StatusDot status={summary?.status ?? "in_progress"} />
            <div className="flex-1 min-w-0">
              <div className="font-serif leading-snug truncate">
                {truncate(summary?.question ?? node.investigationId, 60)}
              </div>
              <div className="font-mono text-[9px] text-ink-mute dark:text-moonlight mt-0.5">
                {summary?.cost_usd_total
                  ? `$${summary.cost_usd_total.toFixed(4)}`
                  : "$0"}
                {summary?.started_at && ` · ${formatRelative(summary.started_at)}`}
              </div>
            </div>
          </div>
        </NavLink>
      </div>
      {expanded && node.children.length > 0 && (
        <ul className="space-y-1 mt-1">
          {node.children.map((child) => (
            <TreeRow
              key={child.investigationId}
              node={child}
              depth={depth + 1}
              activeId={activeId}
              selecting={selecting}
              selected={selected}
              onToggle={onToggle}
              pending={pending}
            />
          ))}
        </ul>
      )}
    </li>
  );
}

function StatusDot({ status }: { status: InvestigationSummary["status"] }) {
  const color =
    status === "in_progress"
      ? "bg-sun animate-pulse"
      : status === "completed"
        ? "bg-aurora"
        : status === "failed"
          ? "bg-emperor"
          : "bg-ink-mute dark:bg-moonlight";
  return (
    <span
      className={`w-1.5 h-1.5 rounded-full mt-1.5 shrink-0 ${color}`}
      aria-label={status}
    />
  );
}

function truncate(s: string, n: number): string {
  if (s.length <= n) return s;
  return s.slice(0, n - 1) + "…";
}

function formatRelative(iso: string): string {
  try {
    const then = new Date(iso).getTime();
    const ago = Date.now() - then;
    const seconds = Math.floor(ago / 1000);
    if (seconds < 60) return `${seconds}s ago`;
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return `${minutes}m ago`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours}h ago`;
    const days = Math.floor(hours / 24);
    if (days < 30) return `${days}d ago`;
    return new Date(iso).toLocaleDateString();
  } catch {
    return "";
  }
}
