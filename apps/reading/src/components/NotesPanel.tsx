import { useEffect, useMemo, useRef } from "react";

import type {
  Claim,
  ClaimChallengeRaisedPayload,
  ClaimGroundingCheckFailedPayload,
  ClaimGroundingCheckPassedPayload,
  DispatchCallPayload,
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
import { useOpenDocument } from "../lib/openDocument";

type GroundingFailureReason = NonNullable<
  Extract<GroundingStatus, { result: "failed" }>
>["reason"];

interface NotesPanelProps {
  events: Event[];
  status: "connecting" | "open" | "closed" | "error";
  reconnects: number;
  investigationId: string;
  documentId: string | null;
}

function finiteNonNegativeNumber(value: unknown): number | null {
  const parsed =
    typeof value === "number"
      ? value
      : typeof value === "string" && value.trim() !== ""
        ? Number(value)
        : Number.NaN;
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : null;
}

function nonNegativeSafeInteger(value: unknown): number | null {
  const parsed = finiteNonNegativeNumber(value);
  return parsed !== null && Number.isSafeInteger(parsed) ? parsed : null;
}

function nonEmptyString(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed === "" ? null : trimmed;
}

function displayString(value: unknown, fallback: string): string {
  return nonEmptyString(value) ?? fallback;
}

function stringList(value: unknown): string[] {
  return Array.isArray(value)
    ? value.flatMap((item) => {
        const trimmed = nonEmptyString(item);
        return trimmed ? [trimmed] : [];
      })
    : [];
}

function uniqueStringList(value: unknown): string[] {
  return Array.from(new Set(stringList(value)));
}

function safeEvents(events: Event[]): Event[] {
  const seen = new Set<string>();
  return events.flatMap((event) => {
    const eventId = nonEmptyString(event.event_id);
    if (eventId) {
      if (seen.has(eventId)) return [];
      seen.add(eventId);
    }
    return [event];
  });
}

function eventKey(event: Event, index: number): string {
  return [
    nonEmptyString(event.event_id) ?? "missing-event-id",
    nonEmptyString(event.action_type) ?? "unknown-action",
    nonEmptyString(event.emitted_at) ?? "unknown-time",
    index,
  ].join(":");
}

function isClaimConfidence(value: unknown): value is Claim["confidence"] {
  return (
    value === "high" ||
    value === "moderate" ||
    value === "low" ||
    value === "unknown"
  );
}

function safeClaim(value: unknown): Claim | null {
  if (value === null || typeof value !== "object") return null;
  const record = value as Record<string, unknown>;
  const claimId = nonEmptyString(record.claim_id);
  const text = nonEmptyString(record.text);
  if (!claimId || !text) return null;

  return {
    claim_id: claimId,
    text,
    confidence: isClaimConfidence(record.confidence)
      ? record.confidence
      : "unknown",
    attribution_region_ids: uniqueStringList(record.attribution_region_ids),
    node_id:
      typeof record.node_id === "string" || record.node_id === null
        ? record.node_id
        : undefined,
  };
}

function safeClaims(value: unknown): Claim[] {
  if (!Array.isArray(value)) return [];
  const seen = new Set<string>();
  return value.flatMap((item) => {
    const claim = safeClaim(item);
    if (!claim || seen.has(claim.claim_id)) return [];
    seen.add(claim.claim_id);
    return [claim];
  });
}

function isGroundingFailureReason(
  value: unknown,
): value is GroundingFailureReason {
  return (
    value === "absent_from_source" ||
    value === "paraphrased_not_stated" ||
    value === "out_of_scope" ||
    value === "ambiguous"
  );
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
  const openDocument = useOpenDocument();
  const feedEvents = useMemo(() => safeEvents(events), [events]);

  const lastRegion = useMemo(
    () => findLastSelectedRegion(feedEvents, documentId),
    [feedEvents, documentId],
  );

  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [feedEvents.length]);

  const pendingRequestIds = useMemo(
    () => findPendingRequestIds(feedEvents),
    [feedEvents],
  );

  const groundingByClaim = useMemo(
    () => findGroundingByClaim(feedEvents),
    [feedEvents],
  );

  const selectedRegionPages = useMemo(
    () => findSelectedRegionPages(feedEvents, documentId),
    [feedEvents, documentId],
  );

  return (
    <div className="flex flex-col h-full bg-ice-0 dark:bg-charcoal-2 border-l border-rule dark:border-charcoal-1">
      <div className="px-4 py-2 text-xs font-mono bg-ice-3 dark:bg-charcoal-1 border-b border-rule dark:border-charcoal-1 flex items-center justify-between">
        <span className="text-ink-soft dark:text-starlight">trajectory</span>
        <StatusBadge status={status} reconnects={reconnects} />
      </div>
      <div ref={scrollRef} className="flex-1 overflow-auto px-3 py-3">
        {feedEvents.length === 0 ? (
          <div className="text-sm text-ink-mute dark:text-moonlight font-mono">
            no events yet — load a PDF, then ask or highlight.
          </div>
        ) : (
          <ul className="flex flex-col gap-2.5">
            {feedEvents.map((e, index) => (
              <FeedRow
                key={eventKey(e, index)}
                event={e}
                isPending={
                  e.action_type === "distillation.requested" &&
                  pendingRequestIds.has(e.event_id)
                }
                investigationId={investigationId}
                documentId={documentId}
                groundingByClaim={groundingByClaim}
                selectedRegionPages={selectedRegionPages}
                openDocument={openDocument}
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
  investigationId: string;
  documentId: string | null;
  groundingByClaim: Map<string, GroundingStatus>;
  selectedRegionPages: Map<string, number>;
  openDocument: ReturnType<typeof useOpenDocument>;
}

function FeedRow({
  event,
  isPending,
  investigationId,
  documentId,
  groundingByClaim,
  selectedRegionPages,
  openDocument,
}: FeedRowProps) {
  const at = String(event.action_type);

  switch (at) {
    case "distillation.requested":
      return (
        <UserBubble
          kind="ask"
          text={displayString(
            (event.payload as DistillationRequestedPayload).user_prompt,
            "request unavailable",
          )}
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
          payload={p}
          investigationId={investigationId}
          documentId={documentId}
          emittedAt={event.emitted_at}
          groundingByClaim={groundingByClaim}
          selectedRegionPages={selectedRegionPages}
          openDocument={openDocument}
        />
      );
    }

    case "claim.challenge_raised":
      return (
        <UserBubble
          kind="challenge"
          text={displayString(
            (event.payload as ClaimChallengeRaisedPayload).user_question,
            "challenge unavailable",
          )}
          subline={
            "↳ challenging: " +
            truncate(
              displayString(
                (event.payload as ClaimChallengeRaisedPayload).claim_text,
                "claim unavailable",
              ),
              80,
            )
          }
          eventId={event.event_id}
          emittedAt={event.emitted_at}
        />
      );

    case "document.region_selected": {
      const p = event.payload as DocumentRegionSelectedPayload;
      const page = nonNegativeSafeInteger(p.page) ?? "?";
      const excerpt = displayString(p.text_excerpt, "");
      return (
        <SystemRow
          eventId={event.event_id}
          emittedAt={event.emitted_at}
          icon="◇"
          text={`selected p${page}: "${truncate(excerpt, 100)}"`}
        />
      );
    }

    case "document.loaded": {
      const p = event.payload as DocumentLoadedPayload;
      const mediaType = displayString(p.media_type, "document");
      const sizeBytes = finiteNonNegativeNumber(p.size_bytes);
      const sizeText =
        sizeBytes === null ? "? KB" : `${Math.round(sizeBytes / 1024)} KB`;
      const title = nonEmptyString(p.title);
      return (
        <SystemRow
          eventId={event.event_id}
          emittedAt={event.emitted_at}
          icon="◆"
          text={`loaded ${mediaType} (${sizeText}${title ? ` · ${title}` : ""})`}
        />
      );
    }

    case "dispatch.call": {
      const p = event.payload as DispatchCallPayload;
      const inputTokens = nonNegativeSafeInteger(p.input_tokens);
      const outputTokens = nonNegativeSafeInteger(p.output_tokens);
      const costUsd = finiteNonNegativeNumber(p.cost_usd) ?? 0;
      const latencyMs = finiteNonNegativeNumber(p.latency_ms) ?? 0;
      return (
        <SystemRow
          eventId={event.event_id}
          emittedAt={event.emitted_at}
          icon="→"
          text={`${p.provider}/${p.model}  in=${inputTokens ?? "?"} out=${outputTokens ?? "?"} $${costUsd.toFixed(5)} ${Math.round(latencyMs)}ms`}
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
  emittedAt,
  payload,
  investigationId,
  documentId,
  groundingByClaim,
  selectedRegionPages,
  openDocument,
}: {
  eventId: string;
  emittedAt: string;
  payload: DistillationDeliveredPayload;
  investigationId: string;
  documentId: string | null;
  groundingByClaim: Map<string, GroundingStatus>;
  selectedRegionPages: Map<string, number>;
  openDocument: ReturnType<typeof useOpenDocument>;
}) {
  const claims = safeClaims(payload.claims);
  const tokenCount = nonNegativeSafeInteger(payload.token_count);
  const renderedText = nonEmptyString(payload.rendered_text);

  return (
    <li
      id={`event-row-${eventId}`}
      className="flex flex-col items-start gap-1 scroll-mt-4 transition-shadow rounded-md"
    >
      <div className="text-[10px] font-mono text-shadow-1 dark:text-moonlight">
        synthesizer · {claims.length} claim{claims.length === 1 ? "" : "s"} ·{" "}
        {tokenCount ?? "?"} tok
      </div>
      {renderedText && (
        <div className="max-w-[90%] text-sm text-ink dark:text-bright italic bg-ice-1 dark:bg-charcoal-2 border border-rule dark:border-charcoal-1 rounded-md px-3 py-2">
          {renderedText}
        </div>
      )}
      {documentId &&
        claims.map((c) => (
          <div key={c.claim_id} className="w-[90%]">
            <ClaimCard
              claim={c}
              investigationId={investigationId}
              documentId={documentId}
              grounding={groundingByClaim.get(c.claim_id) ?? null}
              onLocateRegion={(regionId) => {
                const selectedPage = selectedRegionPages.get(regionId);
                openDocument(documentId, {
                  page:
                    selectedPage === undefined
                      ? undefined
                      : Math.max(0, selectedPage - 1),
                });
              }}
            />
          </div>
        ))}
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
      const regionId = nonEmptyString(p.region_id);
      if (!regionId) continue;
      return {
        region_id: regionId,
        page: nonNegativeSafeInteger(p.page),
        text_excerpt: displayString(p.text_excerpt, ""),
      };
    }
  }
  return null;
}

function findSelectedRegionPages(
  events: Event[],
  documentId: string | null,
): Map<string, number> {
  const pages = new Map<string, number>();
  if (!documentId) return pages;
  for (const e of events) {
    if (
      e.action_type === "document.region_selected" &&
      e.document_id === documentId
    ) {
      const p = e.payload as DocumentRegionSelectedPayload;
      const regionId = nonEmptyString(p.region_id);
      const page = nonNegativeSafeInteger(p.page);
      if (regionId && page !== null) pages.set(regionId, page);
    }
  }
  return pages;
}

function findPendingRequestIds(events: Event[]): Set<string> {
  const requested = new Set<string>();
  const fulfilled = new Set<string>();
  for (const e of events) {
    if (e.action_type === "distillation.requested") {
      requested.add(e.event_id);
    } else if (e.action_type === "distillation.delivered") {
      const p = e.payload as DistillationDeliveredPayload;
      const requestEventId = nonEmptyString(p.request_event_id);
      if (requestEventId) fulfilled.add(requestEventId);
    }
  }
  for (const fid of fulfilled) requested.delete(fid);
  return requested;
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
      const challengedClaimId = nonEmptyString(p.challenged_claim_id);
      if (challengedClaimId) {
        map.set(challengedClaimId, {
          result: "pending",
          eventId: e.event_id,
        });
      }
      continue;
    }
    if (e.action_type === "claim.grounding_check_passed") {
      const p = e.payload as ClaimGroundingCheckPassedPayload;
      const claimId = nonEmptyString(p.claim_id);
      const locatedRegionId = nonEmptyString(p.located_region_id);
      const confidence = finiteNonNegativeNumber(p.confidence);
      if (claimId && locatedRegionId && confidence !== null) {
        map.set(claimId, {
          result: "passed",
          located_region_id: locatedRegionId,
          confidence: Math.min(confidence, 1),
          eventId: e.event_id,
        });
      }
      continue;
    }
    if (e.action_type === "claim.grounding_check_failed") {
      const p = e.payload as ClaimGroundingCheckFailedPayload;
      const claimId = nonEmptyString(p.claim_id);
      if (claimId && isGroundingFailureReason(p.reason)) {
        map.set(claimId, {
          result: "failed",
          reason: p.reason,
          searched_regions: stringList(p.searched_regions),
          eventId: e.event_id,
        });
      }
    }
  }
  return map;
}

function summarizeContextPack(payload: TypedPayload): string {
  const p =
    payload !== null && typeof payload === "object"
      ? (payload as unknown as Record<string, unknown>)
      : {};
  const targetRole = nonEmptyString(p.target_role) ?? "context";
  const actualTokens = nonNegativeSafeInteger(p.actual_tokens) ?? 0;
  const targetTokens = nonNegativeSafeInteger(p.target_tokens) ?? 0;
  const layerCount = Array.isArray(p.layers) ? p.layers.length : 0;

  return (
    `pack[${targetRole}] ${actualTokens}/${targetTokens}tok ` +
    `· ${layerCount} layer${layerCount === 1 ? "" : "s"}` +
    (p.budget_overrun === true ? " · overflow" : "")
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
