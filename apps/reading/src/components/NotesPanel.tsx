import { useEffect, useMemo, useRef, useState } from "react";

import {
  checkProviderOutcome,
  getDistillationReconciliation,
  providerCheckTerms,
  releaseProvenUnsentHold,
  reservedReleaseTerms,
  type DistillationReconciliation,
  type ProviderCheckTerms,
  type ReservedReleaseTerms,
} from "../api/distillationReconciliation";
import type {
  ClaimChallengeRaisedPayload,
  ClaimGroundingCheckFailedPayload,
  ClaimGroundingCheckPassedPayload,
  DispatchCallPayload,
  DistillationApprovalRequiredPayload,
  DistillationDeliveredPayload,
  DistillationRequestedPayload,
  DocumentLoadedPayload,
  DocumentRegionSelectedPayload,
  Event,
  TypedPayload,
} from "../generated/types";
import ChatInput from "./ChatInput";
import ClaimCard from "./ClaimCard";
import type { GroundingStatus } from "./ClaimCard";

interface NotesPanelProps {
  events: Event[];
  status: "connecting" | "open" | "closed" | "error";
  reconnects: number;
  investigationId: string;
  documentId: string | null;
}

/**
 * Right-column chat feed. Shows the live wrestling trajectory:
 *
 * - ``distillation.requested``  → user-side bubble
 * - ``distillation.delivered``  → claim cards
 * - ``claim.challenge_raised``  → user-side challenge bubble
 * - ``document.region_selected`` → small region-anchor marker
 * - everything else (dispatch.call, context_pack.assembled, etc.)
 *   → muted one-line system row
 *
 * Auto-scrolls to bottom on each new event so the live tail is always
 * in view. Chat input pinned at the bottom; uses the most recently
 * selected region as the question's scope.
 */
export default function NotesPanel({
  events,
  status,
  reconnects,
  investigationId,
  documentId,
}: NotesPanelProps) {
  const scrollRef = useRef<HTMLDivElement>(null);

  const lastRegion = useMemo(
    () => findLastSelectedRegion(events, documentId),
    [events, documentId],
  );

  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [events.length]);

  const pendingRequestIds = useMemo(
    () => findPendingRequestIds(events),
    [events],
  );
  const deliveredRequestIds = useMemo(
    () => findDeliveredRequestIds(events),
    [events],
  );

  const groundingByClaim = useMemo(
    () => findGroundingByClaim(events),
    [events],
  );

  return (
    <div className="flex flex-col h-full bg-ice-0 dark:bg-charcoal-2 border-l border-rule dark:border-charcoal-1">
      <div className="px-4 py-2 text-xs font-mono bg-ice-3 dark:bg-charcoal-1 border-b border-rule dark:border-charcoal-1 flex items-center justify-between">
        <span className="text-ink-soft dark:text-starlight">trajectory</span>
        <StatusBadge status={status} reconnects={reconnects} />
      </div>
      <div ref={scrollRef} className="flex-1 overflow-auto px-3 py-3">
        {events.length === 0 ? (
          <div className="text-sm text-ink-mute dark:text-moonlight font-mono">
            no events yet — load a PDF, then ask or highlight.
          </div>
        ) : (
          <ul className="flex flex-col gap-2.5">
            {events.map((e) => (
              <FeedRow
                key={e.event_id}
                event={e}
                isPending={
                  e.action_type === "distillation.requested" &&
                  pendingRequestIds.has(e.event_id)
                }
                approvalResolved={
                  e.action_type === "distillation.approval_required" &&
                  deliveredRequestIds.has(
                    (e.payload as DistillationApprovalRequiredPayload).request_event_id,
                  )
                }
                investigationId={investigationId}
                documentId={documentId}
                groundingByClaim={groundingByClaim}
              />
            ))}
          </ul>
        )}
      </div>
      <ChatInput
        investigationId={investigationId}
        documentId={documentId}
        region={lastRegion}
        disabled={documentId === null}
      />
    </div>
  );
}


// ---------------------------------------------------------------------------
// Feed rows
// ---------------------------------------------------------------------------

interface FeedRowProps {
  event: Event;
  isPending: boolean;
  approvalResolved: boolean;
  investigationId: string;
  documentId: string | null;
  groundingByClaim: Map<string, GroundingStatus>;
}

function FeedRow({
  event,
  isPending,
  approvalResolved,
  investigationId,
  documentId,
  groundingByClaim,
}: FeedRowProps) {
  const at = String(event.action_type);

  switch (at) {
    case "distillation.requested":
      return (
        <UserBubble
          kind="ask"
          text={(event.payload as DistillationRequestedPayload).user_prompt}
          isPending={isPending}
          eventId={event.event_id}
          emittedAt={event.emitted_at}
        />
      );

    case "distillation.delivered": {
      const p = event.payload as DistillationDeliveredPayload;
      return (
        <AssistantClaimsBubble
          eventId={event.event_id}
          policyId={event.policy_id}
          payload={p}
          investigationId={investigationId}
          documentId={documentId}
          emittedAt={event.emitted_at}
          groundingByClaim={groundingByClaim}
        />
      );
    }

    case "distillation.approval_required":
      return (
        <ApprovalRequiredRow
          eventId={event.event_id}
          emittedAt={event.emitted_at}
          payload={event.payload as DistillationApprovalRequiredPayload}
          resolved={approvalResolved}
        />
      );

    case "claim.challenge_raised":
      return (
        <UserBubble
          kind="challenge"
          text={(event.payload as ClaimChallengeRaisedPayload).user_question}
          subline={
            "↳ challenging: " +
            truncate((event.payload as ClaimChallengeRaisedPayload).claim_text, 80)
          }
          eventId={event.event_id}
          emittedAt={event.emitted_at}
        />
      );

    case "document.region_selected": {
      const p = event.payload as DocumentRegionSelectedPayload;
      return (
        <SystemRow
          eventId={event.event_id}
          emittedAt={event.emitted_at}
          icon="◇"
          text={`selected p${p.page ?? "?"}: "${truncate(p.text_excerpt, 100)}"`}
        />
      );
    }

    case "document.loaded": {
      const p = event.payload as DocumentLoadedPayload;
      return (
        <SystemRow
          eventId={event.event_id}
          emittedAt={event.emitted_at}
          icon="◆"
          text={`loaded ${p.media_type} (${Math.round(p.size_bytes / 1024)} KB${p.title ? ` · ${p.title}` : ""})`}
        />
      );
    }

    case "dispatch.call": {
      const p = event.payload as DispatchCallPayload;
      return (
        <SystemRow
          eventId={event.event_id}
          emittedAt={event.emitted_at}
          icon="→"
          text={`${p.provider}/${p.model}  in=${p.input_tokens} out=${p.output_tokens} $${p.cost_usd.toFixed(5)} ${p.latency_ms}ms`}
          tone="muted"
        />
      );
    }

    case "context_pack.assembled":
      return (
        <SystemRow
          eventId={event.event_id}
          emittedAt={event.emitted_at}
          icon="□"
          text={summarizeContextPack(event.payload)}
          tone="muted"
        />
      );

    default:
      return (
        <SystemRow
          eventId={event.event_id}
          emittedAt={event.emitted_at}
          icon="·"
          text={at}
          tone="muted"
        />
      );
  }
}


// ---------------------------------------------------------------------------
// Bubble variants
// ---------------------------------------------------------------------------

function UserBubble({
  kind,
  text,
  subline,
  isPending,
  eventId,
  emittedAt,
}: {
  kind: "ask" | "challenge";
  text: string;
  subline?: string;
  isPending?: boolean;
  eventId: string;
  emittedAt: string;
}) {
  const label = kind === "ask" ? "you" : "you · challenge";
  return (
    <li
      id={`event-row-${eventId}`}
      className="flex flex-col items-end gap-0.5 scroll-mt-4 transition-shadow rounded-md"
    >
      <div className="max-w-[85%] bg-blue-50 border border-blue-100 rounded-md px-3 py-2">
        <div className="text-[10px] font-mono text-blue-700 mb-0.5">{label}</div>
        <p className="text-sm text-ink dark:text-bright whitespace-pre-wrap">{text}</p>
        {subline && (
          <div className="mt-1 text-[10px] font-mono text-shadow-1 dark:text-moonlight italic">
            {subline}
          </div>
        )}
        {isPending && (
          <div className="mt-1 text-[10px] font-mono text-sun-deep dark:text-sun">
            ⏳ waiting for synthesizer…
          </div>
        )}
      </div>
      <EventMeta eventId={eventId} emittedAt={emittedAt} align="right" />
    </li>
  );
}

function AssistantClaimsBubble({
  eventId,
  policyId,
  emittedAt,
  payload,
  investigationId,
  documentId,
  groundingByClaim,
}: {
  eventId: string;
  policyId: string | undefined;
  emittedAt: string;
  payload: DistillationDeliveredPayload;
  investigationId: string;
  documentId: string | null;
  groundingByClaim: Map<string, GroundingStatus>;
}) {
  return (
    <li
      id={`event-row-${eventId}`}
      className="flex flex-col items-start gap-1 scroll-mt-4 transition-shadow rounded-md"
    >
      <div className="text-[10px] font-mono text-shadow-1 dark:text-moonlight">
        synthesizer · {payload.claims.length} claim
        {payload.claims.length === 1 ? "" : "s"} · {payload.token_count} tok
      </div>
      {payload.rendered_text && (
        <div className="max-w-[90%] text-sm text-ink dark:text-bright italic bg-ice-1 dark:bg-charcoal-2 border border-rule dark:border-charcoal-1 rounded-md px-3 py-2">
          {payload.rendered_text}
        </div>
      )}
      {policyId === "wrestling-fallback/ambiguous" && (
        <DistillationReconciliationControl
          requestEventId={payload.request_event_id}
        />
      )}
      {documentId &&
        payload.claims.map((c) => (
          <div key={c.claim_id} className="w-[90%]">
            <ClaimCard
              claim={c}
              investigationId={investigationId}
              documentId={documentId}
              grounding={groundingByClaim.get(c.claim_id) ?? null}
            />
          </div>
        ))}
      <EventMeta eventId={eventId} emittedAt={emittedAt} align="left" />
    </li>
  );
}

function DistillationReconciliationControl({
  requestEventId,
}: {
  requestEventId: string;
}) {
  const [view, setView] = useState<DistillationReconciliation | null>(null);
  const [releaseTerms, setReleaseTerms] = useState<ReservedReleaseTerms | null>(null);
  const [checkTerms, setCheckTerms] = useState<ProviderCheckTerms | null>(null);
  const [errorKind, setErrorKind] = useState<"evidence" | "stale">("evidence");
  const actionInFlight = useRef(false);
  const [phase, setPhase] = useState<"idle" | "loading" | "review" | "releasing" | "done" | "error">("idle");

  async function review(): Promise<void> {
    setErrorKind("evidence");
    setPhase("loading");
    try {
      const next = await getDistillationReconciliation(requestEventId);
      setView(next);
      if (next.next_action === "release_proven_unsent") {
        setReleaseTerms(reservedReleaseTerms(next));
        setCheckTerms(null);
      } else if (next.next_action === "provider_lookup_required" && next.action_executable) {
        setReleaseTerms(null);
        setCheckTerms(providerCheckTerms(next));
      } else {
        setReleaseTerms(null);
        setCheckTerms(null);
      }
      setPhase("review");
    } catch {
      setView(null);
      setReleaseTerms(null);
      setCheckTerms(null);
      setPhase("error");
    }
  }

  async function release(): Promise<void> {
    if (releaseTerms === null || actionInFlight.current) return;
    actionInFlight.current = true;
    setPhase("releasing");
    try {
      const next = await releaseProvenUnsentHold(requestEventId, releaseTerms);
      setView(next);
      setReleaseTerms(null);
      setCheckTerms(null);
      setPhase("done");
    } catch {
      setView(null);
      setReleaseTerms(null);
      setCheckTerms(null);
      setErrorKind("stale");
      setPhase("error");
    } finally {
      actionInFlight.current = false;
    }
  }

  async function checkProvider(): Promise<void> {
    if (checkTerms === null || actionInFlight.current) return;
    actionInFlight.current = true;
    setPhase("releasing");
    try {
      const next = await checkProviderOutcome(requestEventId, checkTerms);
      setView(next);
      setReleaseTerms(null);
      setCheckTerms(
        next.next_action === "provider_lookup_required" && next.action_executable
          ? providerCheckTerms(next)
          : null,
      );
      setPhase(next.next_action === "none" ? "done" : "review");
    } catch {
      setView(null);
      setReleaseTerms(null);
      setCheckTerms(null);
      setErrorKind("stale");
      setPhase("error");
    } finally {
      actionInFlight.current = false;
    }
  }

  if (phase === "idle") {
    return (
      <button type="button" className="text-xs font-medium underline" onClick={() => void review()}>
        Review held budget
      </button>
    );
  }
  if (phase === "loading") {
    return <div className="text-xs font-mono text-ink-soft">Checking spend evidence…</div>;
  }
  if (phase === "error") {
    return (
      <div className="flex flex-col items-start gap-1 text-xs">
        <span>
          {errorKind === "stale"
            ? "Hold state changed. Review current terms before trying again. Budget remains held."
            : "Spend evidence is unavailable. Budget remains held."}
        </span>
        <button type="button" className="font-medium underline" onClick={() => void review()}>
          Retry evidence check
        </button>
      </div>
    );
  }
  if (phase === "done") {
    const terminal = view?.holds.at(-1)?.state;
    return (
      <div className="text-xs font-mono">
        {terminal === "settled"
          ? "Provider charge verified · hold settled"
          : terminal === "released"
            ? "Hold released · budget restored"
            : "Reconciliation complete"}
      </div>
    );
  }
  if (view?.next_action === "provider_lookup_required") {
    if (!view.action_executable || checkTerms === null) {
      return (
        <div className="text-xs font-mono">
          Provider verification required · budget remains held
        </div>
      );
    }
    const hold = view.holds.at(-1)!;
    return (
      <div className="w-[90%] border border-rule dark:border-charcoal-1 rounded-md p-2 text-xs font-mono">
        <div>Provider verification available</div>
        <div>Held ${(hold.projected_max_cents / 100).toFixed(2)} USD</div>
        <div className="break-all">Hold {checkTerms.expected_hold_id}</div>
        <div>Expected hold state {checkTerms.expected_hold_state}</div>
        <button
          type="button"
          className="mt-2 font-medium underline disabled:opacity-50"
          disabled={phase === "releasing"}
          onClick={() => void checkProvider()}
        >
          Check provider outcome
        </button>
      </div>
    );
  }
  if (view?.next_action === "none" || releaseTerms === null || view === null) {
    return <div className="text-xs font-mono">No local budget action is available</div>;
  }
  const hold = view.holds.at(-1)!;
  return (
    <div className="w-[90%] border border-rule dark:border-charcoal-1 rounded-md p-2 text-xs font-mono">
      <div>Reserved ${(hold.projected_max_cents / 100).toFixed(2)} USD</div>
      <div>Command state {releaseTerms.expected_command_state}</div>
      <div className="break-all">Run {view.spend_run_id}</div>
      <div className="break-all">Chain {view.fallback_chain_id}</div>
      <div className="break-all">Manifest {view.manifest_sha256}</div>
      <div>Fallback route {releaseTerms.expected_fallback_index}</div>
      <div className="break-all">Hold {view.current_hold_id}</div>
      <div>Expected hold state {releaseTerms.expected_hold_state}</div>
      <button
        type="button"
        className="mt-2 font-medium underline disabled:opacity-50"
        disabled={phase === "releasing"}
        onClick={() => void release()}
      >
        {phase === "releasing" ? "Releasing reserved hold…" : "Release reserved hold"}
      </button>
    </div>
  );
}

function ApprovalRequiredRow({
  eventId,
  emittedAt,
  payload,
  resolved,
}: {
  eventId: string;
  emittedAt: string;
  payload: DistillationApprovalRequiredPayload;
  resolved: boolean;
}) {
  const approvable = payload.reason === "approval_required";
  return (
    <li
      id={`event-row-${eventId}`}
      className="flex flex-col gap-1 rounded-md border border-rule dark:border-charcoal-1 px-3 py-2 scroll-mt-4"
    >
      <div className="text-xs font-mono text-ink dark:text-bright">
        {resolved
          ? "Spend approved · completed"
          : approvable
            ? "Spend approval required"
            : "Qualified paid route unavailable"}
      </div>
      {approvable && (
        <div className="text-[11px] font-mono text-ink-soft dark:text-starlight">
          Ceiling ${(payload.ceiling_cents! / 100).toFixed(2)} USD · maximum exposure ${(
            payload.maximum_chain_exposure_cents! / 100
          ).toFixed(2)} USD
        </div>
      )}
      {!resolved && (
        <a
          href="/settings"
          className="w-fit text-xs font-medium text-blue-700 dark:text-sun underline"
        >
          {approvable ? "Review exact terms in Settings" : "Open model settings"}
        </a>
      )}
      <EventMeta eventId={eventId} emittedAt={emittedAt} align="left" />
    </li>
  );
}

function SystemRow({
  eventId,
  emittedAt,
  icon,
  text,
  tone,
}: {
  eventId: string;
  emittedAt: string;
  icon: string;
  text: string;
  tone?: "muted";
}) {
  const color = tone === "muted" ? "text-ink-mute dark:text-moonlight" : "text-ink-soft dark:text-starlight";
  return (
    <li
      id={`event-row-${eventId}`}
      className="flex flex-col gap-0.5 scroll-mt-4 transition-shadow rounded-md"
    >
      <div className={`text-[11px] font-mono ${color} flex gap-1.5`}>
        <span className="w-3 text-center">{icon}</span>
        <span className="truncate">{text}</span>
      </div>
      <EventMeta eventId={eventId} emittedAt={emittedAt} align="left" inline />
    </li>
  );
}

function EventMeta({
  eventId,
  emittedAt,
  align,
  inline,
}: {
  eventId: string;
  emittedAt: string;
  align: "left" | "right";
  inline?: boolean;
}) {
  return (
    <div
      className={`text-[9px] font-mono text-ink-mute dark:text-moonlight ${
        inline ? "ml-5" : ""
      } ${align === "right" ? "self-end" : "self-start"}`}
    >
      {shortenEventId(eventId)} · {shortenIsoTime(emittedAt)}
    </div>
  );
}


// ---------------------------------------------------------------------------
// Status badge
// ---------------------------------------------------------------------------

function StatusBadge({
  status,
  reconnects,
}: {
  status: NotesPanelProps["status"];
  reconnects: number;
}) {
  const color =
    status === "open"
      ? "bg-emerald-500"
      : status === "connecting"
      ? "bg-sun/100"
      : "bg-red-500";
  return (
    <span className="inline-flex items-center gap-1.5 text-ink dark:text-bright">
      <span className={`inline-block h-2 w-2 rounded-full ${color}`} />
      <span>{status}</span>
      {reconnects > 0 && (
        <span className="text-ink-mute dark:text-moonlight">
          · {reconnects} reconnect{reconnects === 1 ? "" : "s"}
        </span>
      )}
    </span>
  );
}


// ---------------------------------------------------------------------------
// Derivation helpers
// ---------------------------------------------------------------------------

function findLastSelectedRegion(
  events: Event[],
  documentId: string | null,
): { region_id: string; page: number | null; text_excerpt: string } | null {
  if (!documentId) return null;
  for (let i = events.length - 1; i >= 0; i--) {
    const e = events[i];
    if (
      e.action_type === "document.region_selected" &&
      e.document_id === documentId
    ) {
      const p = e.payload as DocumentRegionSelectedPayload;
      return {
        region_id: p.region_id,
        page: p.page ?? null,
        text_excerpt: p.text_excerpt,
      };
    }
  }
  return null;
}

function findPendingRequestIds(events: Event[]): Set<string> {
  const requested = new Set<string>();
  const noLongerDispatching = new Set<string>();
  for (const e of events) {
    if (e.action_type === "distillation.requested") {
      requested.add(e.event_id);
    } else if (e.action_type === "distillation.delivered") {
      const p = e.payload as DistillationDeliveredPayload;
      noLongerDispatching.add(p.request_event_id);
    } else if (e.action_type === "distillation.approval_required") {
      const p = e.payload as DistillationApprovalRequiredPayload;
      noLongerDispatching.add(p.request_event_id);
    }
  }
  for (const requestId of noLongerDispatching) requested.delete(requestId);
  return requested;
}

function findDeliveredRequestIds(events: Event[]): Set<string> {
  const delivered = new Set<string>();
  for (const event of events) {
    if (event.action_type === "distillation.delivered") {
      delivered.add((event.payload as DistillationDeliveredPayload).request_event_id);
    }
  }
  return delivered;
}


/**
 * Walks the event stream and returns a per-claim grounding map:
 *
 * 1. Find every ``claim.challenge_raised`` keyed on
 *    ``challenged_claim_id`` → mark as "pending".
 * 2. Replace with "passed" / "failed" when a
 *    ``claim.grounding_check_passed`` / ``_failed`` references the
 *    same claim. Last verdict wins (a re-challenge of the same claim
 *    surfaces the freshest result).
 *
 * Claims that have never been challenged don't appear in the map.
 */
function findGroundingByClaim(events: Event[]): Map<string, GroundingStatus> {
  const map = new Map<string, GroundingStatus>();
  for (const e of events) {
    if (e.action_type === "claim.challenge_raised") {
      const p = e.payload as ClaimChallengeRaisedPayload;
      if (p.challenged_claim_id) {
        map.set(p.challenged_claim_id, {
          result: "pending",
          eventId: e.event_id,
        });
      }
      continue;
    }
    if (e.action_type === "claim.grounding_check_passed") {
      const p = e.payload as ClaimGroundingCheckPassedPayload;
      if (p.claim_id) {
        map.set(p.claim_id, {
          result: "passed",
          located_region_id: p.located_region_id,
          confidence: p.confidence,
          eventId: e.event_id,
        });
      }
      continue;
    }
    if (e.action_type === "claim.grounding_check_failed") {
      const p = e.payload as ClaimGroundingCheckFailedPayload;
      if (p.claim_id) {
        map.set(p.claim_id, {
          result: "failed",
          reason: p.reason,
          searched_regions: p.searched_regions,
          eventId: e.event_id,
        });
      }
    }
  }
  return map;
}

function summarizeContextPack(payload: TypedPayload): string {
  // Avoid pulling in the full ContextPackAssembledPayload type for one
  // formatting line; cast through unknown.
  const p = payload as unknown as {
    target_role: string;
    actual_tokens: number;
    target_tokens: number;
    layers: { kind: string; tokens: number }[];
    budget_overrun: boolean;
  };
  return (
    `pack[${p.target_role}] ${p.actual_tokens}/${p.target_tokens}tok ` +
    `· ${p.layers.length} layer${p.layers.length === 1 ? "" : "s"}` +
    (p.budget_overrun ? " · overflow" : "")
  );
}

function truncate(s: string, n: number): string {
  return s.length <= n ? s : s.slice(0, n) + "…";
}

function shortenEventId(id: string): string {
  return id.length > 14 ? id.slice(0, 16) : id;
}

function shortenIsoTime(iso: string): string {
  // Strip date when it's today's date; show HH:MM:SS for compactness.
  // Today vs not-today is checked against the client clock; close
  // enough for an audit-feed UI.
  const m = /T(\d\d:\d\d:\d\d)/.exec(iso);
  return m ? m[1] : iso;
}
