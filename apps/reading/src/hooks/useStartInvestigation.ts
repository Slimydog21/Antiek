import { useCallback, useLayoutEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import {
  ApiError, publishStartCapacityEffect, startInvestigation,
  type ResearchSourcePolicy, type ResearchTier, type StartInvestigationRequest,
  type StartInvestigationResponse,
} from "../lib/api";
import { CapacityExhaustedError } from "../lib/capacityWarn";
import { useAuth } from "../lib/auth";
import { parseModelIdentity, type ReadyModelScope } from "../lib/modelExecutionScope";
import type { Event } from "../generated/types";
import type { OwnerModelController, PreparedModelLaunch } from "./useOwnerModelController";
import { useEventStream } from "./useEventStream";
import {
  rootResearchLaunchArchive, type RootResearchIntent, type RootResearchLaunchHandle,
} from "../modes/ResearchWorkstation/rootResearchLaunch";

const LEGACY_KEY = "antiek.research.pending-owner-launch.session.v1";
const UNRESOLVED_KEY = "antiek.research.unresolved-owner-launch.session.v2";
const UNCERTAIN_MESSAGE = "Could not confirm the start. The request may have been accepted or charged.";
const STORAGE_MESSAGE = "Cannot verify previous research requests in this browser. No new request was sent.";
const CONNECT_MODEL_MESSAGE = "Choose a model in Settings. The previous request may have been accepted or charged.";

type OwnerProjection = Readonly<{
  user_id: string;
  email: string | null;
  auth_method: string;
  operator_email_discriminator: string | null;
}>;
type StoredHold = Readonly<{ owner: OwnerProjection; operation_id: string }>;
type Continuity =
  | Readonly<{ kind: "unavailable" }>
  | Readonly<{
      kind: "available";
      owner: OwnerProjection;
      holds: readonly StoredHold[];
      legacy: string | null;
      signature: string;
      hasHolds: boolean;
    }>;
function record(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
function projectOwner(value: unknown): OwnerProjection | null {
  const identity = parseModelIdentity(value);
  if (!identity) return null;
  return Object.freeze({
    ...identity,
    operator_email_discriminator: identity.user_id.trim().toLowerCase() === "__operator__"
      ? identity.email?.trim().toLowerCase() ?? null : null,
  });
}
function ownerKey(owner: OwnerProjection): string {
  return JSON.stringify([owner.user_id, owner.email, owner.auth_method, owner.operator_email_discriminator]);
}
function parseHolds(raw: string | null): readonly StoredHold[] | null {
  if (raw === null) return [];
  try {
    const value: unknown = JSON.parse(raw);
    if (!record(value) || value.version !== 2 || !Array.isArray(value.holds) ||
        Object.keys(value).some((key) => key !== "version" && key !== "holds")) return null;
    const result: StoredHold[] = [];
    const seen = new Set<string>();
    for (const hold of value.holds) {
      if (!record(hold) || !record(hold.owner) ||
          Object.keys(hold).some((key) => key !== "owner" && key !== "operation_id") ||
          typeof hold.operation_id !== "string" || !hold.operation_id.trim()) return null;
      const owner = projectOwner(hold.owner);
      if (!owner || owner.operator_email_discriminator !== hold.owner.operator_email_discriminator ||
          Object.keys(hold.owner).some((key) =>
            !["user_id", "email", "auth_method", "operator_email_discriminator"].includes(key))) return null;
      const key = JSON.stringify([ownerKey(owner), hold.operation_id]);
      if (seen.has(key)) return null;
      seen.add(key);
      result.push(Object.freeze({ owner, operation_id: hold.operation_id }));
    }
    return Object.freeze(result);
  } catch {
    return null;
  }
}
function readContinuity(scope: ReadyModelScope): Continuity {
  const owner = projectOwner(scope.identity);
  if (!owner) return { kind: "unavailable" };
  try {
    const holds = parseHolds(window.sessionStorage.getItem(UNRESOLVED_KEY));
    const legacy = window.sessionStorage.getItem(LEGACY_KEY);
    if (!holds) return { kind: "unavailable" };
    const relevant = holds.filter((hold) => ownerKey(hold.owner) === ownerKey(owner))
      .map((hold) => hold.operation_id).sort();
    return { kind: "available", owner, holds, legacy,
      signature: JSON.stringify([ownerKey(owner), relevant, legacy]),
      hasHolds: relevant.length > 0 || legacy !== null };
  } catch {
    return { kind: "unavailable" };
  }
}
function writeHold(snapshot: Extract<Continuity, { kind: "available" }>, operationId: string): boolean {
  try {
    const holds = parseHolds(window.sessionStorage.getItem(UNRESOLVED_KEY));
    if (!holds || window.sessionStorage.getItem(LEGACY_KEY) !== snapshot.legacy) return false;
    const relevant = holds.filter((hold) => ownerKey(hold.owner) === ownerKey(snapshot.owner))
      .map((hold) => hold.operation_id).sort();
    if (JSON.stringify([ownerKey(snapshot.owner), relevant, snapshot.legacy]) !== snapshot.signature ||
        holds.some((hold) => hold.operation_id === operationId && ownerKey(hold.owner) === ownerKey(snapshot.owner))) return false;
    const raw = JSON.stringify({ version: 2, holds: [...holds, { owner: snapshot.owner, operation_id: operationId }] });
    window.sessionStorage.setItem(UNRESOLVED_KEY, raw);
    return window.sessionStorage.getItem(UNRESOLVED_KEY) === raw && window.sessionStorage.getItem(LEGACY_KEY) === snapshot.legacy;
  } catch {
    return false;
  }
}
function removeOwnHold(owner: OwnerProjection, operationId: string): boolean {
  try {
    const holds = parseHolds(window.sessionStorage.getItem(UNRESOLVED_KEY));
    if (!holds) return false;
    const remaining = holds.filter((hold) => hold.operation_id !== operationId || ownerKey(hold.owner) !== ownerKey(owner));
    if (remaining.length === holds.length) return true;
    if (remaining.length === 0) {
      window.sessionStorage.removeItem(UNRESOLVED_KEY);
      return window.sessionStorage.getItem(UNRESOLVED_KEY) === null;
    }
    const raw = JSON.stringify({ version: 2, holds: remaining });
    window.sessionStorage.setItem(UNRESOLVED_KEY, raw);
    return window.sessionStorage.getItem(UNRESOLVED_KEY) === raw;
  } catch {
    return false;
  }
}
function isConnectModelError(error: unknown): boolean {
  if (!(error instanceof ApiError) || error.status !== 409) return false;
  try {
    const response: unknown = JSON.parse(error.body);
    return record(response) && response.detail === "connect_model";
  } catch {
    return false;
  }
}
function validOwnerReceipt(value: unknown, operationId: string): value is StartInvestigationResponse {
  return record(value) && typeof value.investigation_id === "string" && !!value.investigation_id.trim() &&
    typeof value.start_event_id === "string" && !!value.start_event_id.trim() && value.status === "started" &&
    value.operation_id === operationId && (value.owner_model_status === "queued" || value.owner_model_status === "replayed");
}
export type StartPhase = "idle" | "posting" | "connecting" | "streaming" | "failed" | "error";
export interface DeepResearchDraft {
  question: string;
  researchTier: ResearchTier;
  sourcePolicy: readonly ResearchSourcePolicy[];
  revision: object;
}
export interface StartInvestigationOptions {
  controller: OwnerModelController;
  /** A private observed home lifetime. Null refuses paid admission. */
  readHome: () => object | null;
  isHomeCurrent: (home: object) => boolean;
  isAdmitted: () => boolean;
  /** Stable for one committed deep-mode lifetime, null outside it. */
  readAdmission: () => object | null;
  readDraftRevision: () => object;
}
export interface StartInvestigationState {
  startedId: string | null;
  phase: StartPhase;
  events: Event[];
  liveCost: number;
  failed: boolean;
  failureReason: string | null;
  error: string | null;
  busy: boolean;
  showUncertainty: boolean;
  /** The consumed intent needs an explicit separate paid action. */
  requiresNewIntent: boolean;
  continuityUnavailable: boolean;
  submitDisabled: boolean;
  submit: (input: DeepResearchDraft) => Promise<string | null>;
  /** Acknowledges the exact current holds. Does not dispatch or replay. */
  startSeparate: () => boolean;
  isIssued: () => boolean;
  isDeliveryCurrent: (investigationId?: string) => boolean;
  reportDeliveryFailure: (investigationId: string, message?: string) => void;
  reset: () => void;
}
type Issued = Readonly<{
  scope: ReadyModelScope;
  home: object;
  admission: object;
  revision: object;
  request: Readonly<StartInvestigationRequest>;
  prepared: Extract<PreparedModelLaunch, { kind: "saved" }>;
  owner: OwnerProjection;
  handle: RootResearchLaunchHandle;
}>;
type Delivery = { issued: Issued; kind: "pending" | "unknown" | "received"; id: string | null; error: string | null };
type Acknowledgment = Readonly<{ scope: ReadyModelScope; home: object; admission: object; signature: string; intent: RootResearchIntent }>;

/** One issued paid action, with private delivery fencing and no POST retry. */
export function useStartInvestigation(options: StartInvestigationOptions): StartInvestigationState {
  const { modelExecution } = useAuth();
  const renderedScope = modelExecution.current;
  const renderedHome = options.readHome();
  const renderedAdmission = options.readAdmission();
  useSyncExternalStore(rootResearchLaunchArchive.subscribe, rootResearchLaunchArchive.getVersion, rootResearchLaunchArchive.getVersion);
  const mounted = useRef(false);
  const live = useRef({ options, modelExecution });
  useLayoutEffect(() => { live.current = { options, modelExecution }; });
  useLayoutEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  const intent = useRef<RootResearchIntent | null>(null);
  useLayoutEffect(() => { intent.current ??= rootResearchLaunchArchive.createIntent(); }, []);
  const acknowledgment = useRef<Acknowledgment | null>(null);
  const issuing = useRef(false);
  const issued = useRef<Issued | null>(null);
  const delivery = useRef<Delivery | null>(null);
  const [, renderAction] = useState(0);
  const notify = useCallback(() => { if (mounted.current) renderAction((v) => v + 1); }, []);
  const validation = useRef<{ scope: ReadyModelScope; home: object; admission: object; revision: object; message: string } | null>(null);
  const isLive = useCallback((action: Issued): boolean => {
    const current = live.current;
    return mounted.current && issued.current === action && current.modelExecution.readCurrent() === action.scope &&
      current.options.isHomeCurrent(action.home) && current.options.readAdmission() === action.admission && current.options.readDraftRevision() === action.revision && current.options.isAdmitted();
  }, []);
  const isIssued = useCallback(() => issuing.current || delivery.current?.kind === "pending", []);
  const isDeliveryCurrent = useCallback((id?: string) => {
    const progress = delivery.current;
    return !!progress && progress.kind === "received" && isLive(progress.issued) && (id === undefined || progress.id === id);
  }, [isLive]);
  const archiveSnapshotMatches = (candidate: RootResearchIntent): boolean => {
    try {
      const holds = rootResearchLaunchArchive.createIntent(true).separateFrom;
      return candidate.separateFrom === null ? !holds?.length :
        JSON.stringify(candidate.separateFrom) === JSON.stringify(holds);
    } catch {
      return false;
    }
  };
  const submit = useCallback(async (input: DeepResearchDraft): Promise<string | null> => {
    const current = live.current;
    const scope = current.modelExecution.readCurrent();
    const home = current.options.readHome();
    const admission = current.options.readAdmission();
    if (!mounted.current || scope.kind !== "ready" || scope !== renderedScope || !home || home !== renderedHome ||
        !admission || admission !== renderedAdmission ||
        !current.options.isHomeCurrent(home) || !current.options.isAdmitted() ||
        current.options.readDraftRevision() !== input.revision || isIssued()) return null;
    const refuse = (message: string) => {
      validation.current = { scope, home, admission, revision: input.revision, message }; notify(); return null;
    };
    const question = input.question.trim();
    if (question.length < 3) return refuse("Question is too short. At least 3 characters.");
    if ((input.researchTier !== "fast" && input.researchTier !== "deep") || !input.sourcePolicy.length ||
        input.sourcePolicy.some((source) => !["operator_corpus", "web", "arxiv", "substack"].includes(source))) {
      return refuse("Choose a research depth and at least one source.");
    }
    const continuity = readContinuity(scope);
    if (continuity.kind === "unavailable") return refuse(STORAGE_MESSAGE);
    const nextIntent = intent.current;
    const ack = acknowledgment.current;
    if (!nextIntent || !rootResearchLaunchArchive.canBegin(nextIntent) || !archiveSnapshotMatches(nextIntent) ||
        (continuity.hasHolds && (!ack || ack.scope !== scope || ack.home !== home || ack.admission !== admission || ack.signature !== continuity.signature || ack.intent !== nextIntent)) ||
        (ack && (ack.scope !== scope || ack.home !== home || ack.admission !== admission || ack.signature !== continuity.signature))) {
      return refuse("A previous request may have been accepted or charged. Confirm a separate paid research before sending another.");
    }
    const policy = [...input.sourcePolicy];
    Object.freeze(policy);
    let prepared: PreparedModelLaunch;
    try {
      prepared = current.options.controller.prepareLaunch({ semanticKey: JSON.stringify([nextIntent.nonce, question, input.researchTier, policy]) });
      if (prepared.kind !== "saved" || !current.options.controller.isCurrent(prepared) || prepared.scope !== current.modelExecution.readCurrent()) {
        return refuse("Choose an executable saved model before starting deep research.");
      }
    } catch {
      return refuse("Could not prepare this research request. No new request was sent.");
    }
    const request = Object.freeze({ question, research_tier: input.researchTier, source_policy: policy,
      model_choice: prepared.fields.model_choice, operation_id: prepared.fields.operation_id });
    // Final admission, marker write, archive begin and dispatch have no await.
    try {
      if (!current.options.isHomeCurrent(home) || current.options.readAdmission() !== admission || !current.options.isAdmitted() ||
          current.options.readDraftRevision() !== input.revision || !current.options.controller.isCurrent(prepared) ||
          current.modelExecution.readCurrent() !== prepared.scope || !archiveSnapshotMatches(nextIntent)) return null;
    } catch {
      return refuse("Could not prepare this research request. No new request was sent.");
    }
    issuing.current = true;
    if (!writeHold(continuity, prepared.fields.operation_id)) { issuing.current = false; return refuse(STORAGE_MESSAGE); }
    let handle: RootResearchLaunchHandle | null = null;
    try { if (archiveSnapshotMatches(nextIntent)) handle = rootResearchLaunchArchive.begin(nextIntent, request, prepared); } catch { /* No dispatch occurred. */ }
    if (!handle) {
      removeOwnHold(continuity.owner, prepared.fields.operation_id);
      issuing.current = false;
      return refuse("A previous request changed while preparing. No new request was sent.");
    }
    const action: Issued = Object.freeze({ scope, home, admission, revision: input.revision, request, prepared, owner: continuity.owner, handle });
    issued.current = action;
    const progress: Delivery = { issued: action, kind: "pending", id: null, error: null };
    delivery.current = progress;
    acknowledgment.current = null;
    validation.current = null;
    issuing.current = false;
    notify();
    try {
      const response: unknown = await startInvestigation(request, { capacityEffects: "deferred" });
      if (!validOwnerReceipt(response, action.prepared.fields.operation_id)) throw new Error("Invalid owner start receipt");
      let accepted = false;
      try { accepted = rootResearchLaunchArchive.accepted(action.handle, response); }
      catch {
        // Publication follows recording. The known-receipt path verifies a
        // recorded result without publishing to a throwing subscriber again.
        try { accepted = rootResearchLaunchArchive.accepted(action.handle, response); } catch { /* Retain continuity. */ }
      }
      if (!accepted) throw new Error("Owner start receipt was not archived");
      progress.kind = "received";
      progress.id = response.investigation_id;
      removeOwnHold(action.owner, action.prepared.fields.operation_id);
      if (!isLive(action)) return null;
      if (response.capacity_warning) {
        try { publishStartCapacityEffect({ kind: "soft", investigationId: response.investigation_id, warning: response.capacity_warning }); }
        catch { progress.error = "The research start was received, but its capacity notice could not be displayed."; }
      }
      return response.investigation_id;
    } catch (error) {
      if (progress.kind === "received") {
        progress.error = "The research start was received, but it could not be displayed here."; return null;
      }
      progress.kind = "unknown";
      try { rootResearchLaunchArchive.uncertain(action.handle); } catch { /* Marker retains continuity. */ }
      if (!isLive(action)) return null;
      progress.error = isConnectModelError(error) ? CONNECT_MODEL_MESSAGE : error instanceof CapacityExhaustedError
        ? `${error.message} ${UNCERTAIN_MESSAGE}` : UNCERTAIN_MESSAGE;
      if (error instanceof CapacityExhaustedError) {
        try { publishStartCapacityEffect({ kind: "hard", exhaustion: error.exhaustion }); } catch { /* Diagnostic delivery cannot permit a retry. */ }
      }
      return null;
    } finally {
      if (issued.current === action) notify();
    }
  }, [renderedScope, renderedHome, renderedAdmission, isIssued, isLive, notify]);
  const startSeparate = useCallback(() => {
    const current = live.current;
    const scope = current.modelExecution.readCurrent();
    const home = current.options.readHome();
    const admission = current.options.readAdmission();
    if (!mounted.current || scope.kind !== "ready" || scope !== renderedScope || !home || home !== renderedHome ||
        !admission || admission !== renderedAdmission || !current.options.isHomeCurrent(home) || !current.options.isAdmitted() || isIssued()) return false;
    const snapshot = readContinuity(scope);
    if (snapshot.kind !== "available") return false;
    const nextIntent = rootResearchLaunchArchive.createIntent(true);
    intent.current = nextIntent;
    acknowledgment.current = Object.freeze({ scope, home, admission, signature: snapshot.signature, intent: nextIntent });
    issued.current = null;
    delivery.current = null;
    validation.current = null;
    notify();
    return true;
  }, [renderedScope, renderedHome, renderedAdmission, isIssued, notify]);
  const reportDeliveryFailure = useCallback((investigationId: string, message?: string) => {
    const progress = delivery.current;
    if (!progress || progress.kind !== "received" || progress.id !== investigationId ||
        progress.issued.scope !== renderedScope || progress.issued.home !== renderedHome ||
        progress.issued.admission !== renderedAdmission || !isLive(progress.issued)) return;
    progress.error = message ?? "The research start was received, but it could not be displayed here.";
    notify();
  }, [renderedScope, renderedHome, renderedAdmission, isLive, notify]);
  const reset = useCallback(() => {
    const current = live.current;
    if (!mounted.current || current.modelExecution.readCurrent() !== renderedScope ||
        !renderedHome || !current.options.isHomeCurrent(renderedHome) ||
        !renderedAdmission || current.options.readAdmission() !== renderedAdmission) return;
    // Hiding delivery never authorizes another POST for an issued intent.
    validation.current = null;
    if (delivery.current && delivery.current.kind !== "pending") delivery.current.id = null;
    notify();
  }, [renderedScope, renderedHome, renderedAdmission, notify]);
  const progress = delivery.current;
  const visible = progress && isLive(progress.issued) ? progress : null;
  const startedId = visible?.kind === "received" ? visible.id : null;
  const stream = useEventStream(startedId);
  const events = useMemo(() => startedId ? stream.events.filter((event) =>
    record(event) && event.investigation_id === startedId && typeof event.action_type === "string") : [], [startedId, stream.events]);
  const liveCost = useMemo(() => events.reduce((cost, event) => {
    const payload = event.payload;
    return event.action_type === "dispatch.call" && record(payload) && typeof payload.cost_usd === "number" ? cost + payload.cost_usd : cost;
  }, 0), [events]);
  const failureReason = useMemo(() => {
    const failure = events.find((event) => event.action_type === "investigation.failed");
    if (!failure) return null;
    return record(failure.payload) && typeof failure.payload.reason === "string" ? failure.payload.reason : "";
  }, [events]);
  const failed = failureReason !== null;
  const current = live.current;
  const scope = current.modelExecution.readCurrent();
  const continuity: Continuity = scope.kind === "ready" ? readContinuity(scope) : { kind: "unavailable" };
  const invalid = validation.current;
  const error = visible?.error ?? (invalid && scope === invalid.scope && current.options.isHomeCurrent(invalid.home) &&
    current.options.readAdmission() === invalid.admission && current.options.readDraftRevision() === invalid.revision ? invalid.message : null);
  const busy = visible?.kind === "pending";
  const phase: StartPhase = busy ? "posting" : failed ? "failed" : startedId ? stream.status === "open" && events.length > 0 ? "streaming" : "connecting" : error ? "error" : "idle";
  const showUncertainty = continuity.kind === "available" && continuity.hasHolds || rootResearchLaunchArchive.hasUnresolved() || visible?.kind === "unknown";
  const ack = acknowledgment.current;
  const acknowledged = continuity.kind === "available" && !!ack && ack.scope === scope && current.options.isHomeCurrent(ack.home) &&
    current.options.readAdmission() === ack.admission && archiveSnapshotMatches(ack.intent) && ack.signature === continuity.signature && ack.intent === intent.current;
  const requiresNewIntent = scope.kind === "ready" && !!current.options.readHome() &&
    current.options.readAdmission() !== null && !!intent.current && !rootResearchLaunchArchive.canBegin(intent.current);
  const submitDisabled = isIssued() || continuity.kind === "unavailable" || !intent.current || !rootResearchLaunchArchive.canBegin(intent.current) || !archiveSnapshotMatches(intent.current) ||
    (continuity.kind === "available" && continuity.hasHolds && !acknowledged) || (ack !== null && !acknowledged);
  return { startedId, phase, events, liveCost, failed, failureReason, error, busy,
    showUncertainty: Boolean(showUncertainty), requiresNewIntent, continuityUnavailable: continuity.kind === "unavailable",
    submitDisabled, submit, startSeparate, isIssued, isDeliveryCurrent, reportDeliveryFailure, reset };
}
