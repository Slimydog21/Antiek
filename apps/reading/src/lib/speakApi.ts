/**
 * speakApi.ts — the Speak data layer (Product Depth SPR-08).
 *
 * The Speak REST surface speaks substrate nouns: `subject_status` and
 * `publish_intent` enums, `project_id`, `interview_id`, corroboration
 * `label`s like `multiply_attested`. Those are correct in the API and the
 * event log and WRONG in front of a user (master-spec §5 + the U-04 language
 * rule). This module is the UI edge: it calls the endpoints and translates
 * the response into plain human shapes, so the substrate enums never reach a
 * rendered component (the copy-lint scans modes/shell/components for them; it
 * does not scan lib/, which is exactly where the translation belongs).
 *
 * It is also the single place the corroboration honesty discipline is encoded
 * for the surface: a `multiply_attested` cluster is rendered as
 * "corroborated", a `contradicted` one as "people disagree" — NEVER "proven"
 * or "true". The label vocabulary the surface may say lives here.
 */
import { apiFetch } from "./api";

/** A person being remembered, translated from a Speak project row. */
export interface RememberedPerson {
  id: string;
  /** The person's name (the subject), falling back to the project title. */
  name: string;
  /** Plain words, not the enum: true when the story will be public. */
  willBePublic: boolean;
  voiceCount: number;
}

/** One arriving voice (an invitee's interview lifecycle row), humanized. */
export type VoiceState =
  | "invited"
  | "recording"
  | "shared"
  | "declined"
  | "unfinished";

export interface ArrivingVoice {
  /** The interview id — used as a stable key + for the share link, never shown. */
  interviewId: string;
  /** The invitee's name/handle/email, or a gentle placeholder. */
  who: string;
  state: VoiceState;
  /** The token-bearing invite link to share. */
  link: string;
}

/**
 * One thing the voices agree (or disagree) on — the honest corroboration
 * surface. `kind` is the ONLY vocabulary the UI may use:
 *   - "corroborated": ≥2 independent voices attest it (never "proven");
 *   - "single": one voice said it (not yet corroborated);
 *   - "disagreement": voices conflict (both sides kept, never resolved here).
 */
export interface AgreementPoint {
  text: string;
  kind: "corroborated" | "single" | "disagreement";
  /** How many independent voices attest it. */
  voices: number;
}

export interface ProjectDetail {
  id: string;
  name: string;
  willBePublic: boolean;
  /** Plain word for the subject's status (e.g. "living", "deceased"), or null. */
  subjectStatusWord: string | null;
}

export interface EconomicsView {
  /** True when public ⇒ the algorithmic contributor split applies. */
  splitApplies: boolean;
  /** True when the creator carries the inference cost (private mode). */
  creatorCarriesCost: boolean;
  /**
   * The operator-gate state (G2/G3), READ-ONLY. The UI surfaces these as
   * "gated / not yet activated" — there is NO close affordance. Closing a
   * gate is an operator action (a deliberate env flip post-counsel), never
   * something this surface can do. Deny-by-default: both false until then.
   */
  publicPublishingAllowed: boolean;
  publicPublishingReason: string;
  disbursementAllowed: boolean;
  disbursementReason: string;
}

/** One project in the browsable PUBLIC feed (M1). */
export interface FeedItem {
  id: string;
  name: string;
  voiceCount: number;
  /** The servable HTML Read asset, absent while this is only public intent. */
  readerDocumentId: string | null;
}

const VOICE_STATE: Record<string, VoiceState> = {
  invited: "invited",
  in_progress: "recording",
  completed: "shared",
  declined: "declined",
  incomplete: "unfinished",
};

export function toPerson(raw: Record<string, unknown>): RememberedPerson {
  const subject = typeof raw.subject_ref === "string" ? raw.subject_ref : null;
  const title = typeof raw.title === "string" ? raw.title : "";
  const publish = typeof raw.publish_intent === "string" ? raw.publish_intent : "";
  const count = typeof raw.interview_count === "number" ? raw.interview_count : 0;
  return {
    id: String(raw.project_id ?? ""),
    name: subject ?? title,
    willBePublic: publish === "will_be_public",
    voiceCount: count,
  };
}

export function toProjectDetail(raw: Record<string, unknown>): ProjectDetail {
  const subject = typeof raw.subject_ref === "string" ? raw.subject_ref : null;
  const title = typeof raw.title === "string" ? raw.title : "";
  const publish = typeof raw.publish_intent === "string" ? raw.publish_intent : "";
  const status = typeof raw.subject_status === "string" ? raw.subject_status : "";
  return {
    id: String(raw.project_id ?? ""),
    name: subject ?? title,
    willBePublic: publish === "will_be_public",
    subjectStatusWord:
      status && status !== "unknown" ? status.replace(/_/g, " ") : null,
  };
}

export function toEconomics(raw: Record<string, unknown>): EconomicsView {
  return {
    splitApplies: Boolean(raw.split_applies),
    creatorCarriesCost: Boolean(raw.creator_carries_cost),
    // Read-only gate state. The backend denies by default; the UI shows
    // these gated and never offers a way to close them.
    publicPublishingAllowed: Boolean(raw.public_publishing_allowed),
    publicPublishingReason:
      typeof raw.public_publishing_reason === "string" ? raw.public_publishing_reason : "",
    disbursementAllowed: Boolean(raw.disbursement_allowed),
    disbursementReason:
      typeof raw.disbursement_reason === "string" ? raw.disbursement_reason : "",
  };
}

export function toVoice(raw: Record<string, unknown>): ArrivingVoice {
  const email = typeof raw.informant_email === "string" ? raw.informant_email : null;
  const handle = typeof raw.informant_handle === "string" ? raw.informant_handle : null;
  const status = typeof raw.status === "string" ? raw.status : "invited";
  return {
    interviewId: String(raw.interview_id ?? ""),
    who: email ?? handle ?? "Someone you invited",
    state: VOICE_STATE[status] ?? "invited",
    link: typeof raw.link === "string" ? raw.link : "",
  };
}

/** Cluster `label` → the honest agreement vocabulary. NEVER returns "proven". */
export function toAgreementKind(label: string): AgreementPoint["kind"] {
  if (label === "multiply_attested") return "corroborated";
  if (label === "contradicted") return "disagreement";
  return "single";
}

// ── calls ──────────────────────────────────────────────────────────────

export async function listPeople(): Promise<RememberedPerson[]> {
  const resp = await apiFetch("/speak/projects");
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  const data = await resp.json();
  const rows: Record<string, unknown>[] = Array.isArray(data.projects) ? data.projects : [];
  return rows.map(toPerson);
}

export async function getProject(id: string): Promise<ProjectDetail> {
  const resp = await apiFetch(`/speak/projects/${encodeURIComponent(id)}`);
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return toProjectDetail(await resp.json());
}

export async function getEconomics(id: string): Promise<EconomicsView> {
  const resp = await apiFetch(`/speak/projects/${encodeURIComponent(id)}/economics`);
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return toEconomics(await resp.json());
}

export async function listVoices(id: string): Promise<ArrivingVoice[]> {
  const resp = await apiFetch(`/speak/projects/${encodeURIComponent(id)}/invites`);
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  const data = await resp.json();
  const rows: Record<string, unknown>[] = Array.isArray(data.invites) ? data.invites : [];
  return rows.map(toVoice);
}

export async function inviteByEmail(id: string, email: string): Promise<ArrivingVoice> {
  const resp = await apiFetch(`/speak/projects/${encodeURIComponent(id)}/invites`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ informant_email: email }),
  });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return toVoice(await resp.json());
}

/** A generic, link-only invite (the shareable "anyone with the link" door for
 *  the warm flow). Backed by a handle so the operator can send it broadly. */
export async function makeShareLink(id: string): Promise<string> {
  const resp = await apiFetch(`/speak/projects/${encodeURIComponent(id)}/invites`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ informant_handle: "a friend or family member" }),
  });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return toVoice(await resp.json()).link;
}

/**
 * The "what everyone agrees on" view. Runs the corroboration pass and maps
 * each cluster onto the honest vocabulary (corroborated / single /
 * disagreement) — NEVER "proven". Throws on a no-key / engine failure so the
 * caller can show the honest no-result state.
 */
export async function whatEveryoneAgreesOn(id: string): Promise<AgreementPoint[]> {
  const resp = await apiFetch(`/speak/projects/${encodeURIComponent(id)}/corroborate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: "{}",
  });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  const data = await resp.json();
  const clusters: Record<string, unknown>[] = Array.isArray(data.clusters) ? data.clusters : [];
  return clusters.map((c) => ({
    text: typeof c.canonical_text === "string" ? c.canonical_text
      : typeof c.label === "string" ? String(c.label).replace(/_/g, " ") : "",
    kind: toAgreementKind(typeof c.label === "string" ? c.label : ""),
    voices: typeof c.independent_attesters === "number" ? c.independent_attesters : 1,
  }));
}

export interface AssembledDraft {
  deliverableId: string;
  prose: string;
  /** Points left out because they aren't corroborated / are contradicted. */
  excludedCount: number;
}

const pendingDraftCommands = new Map<string, string>();
const inFlightDrafts = new Map<string, Promise<AssembledDraft>>();
const DRAFT_COMMAND_PREFIX = "antiek:speak-draft:";

function draftCommand(key: string): string {
  const inMemory = pendingDraftCommands.get(key);
  if (inMemory) return inMemory;
  try {
    const stored = globalThis.localStorage?.getItem(`${DRAFT_COMMAND_PREFIX}${key}`);
    if (stored) return stored;
  } catch {
    // A restricted browser still retains same-tab retry identity in memory.
  }
  return crypto.randomUUID();
}

function persistDraftCommand(key: string, commandId: string | null): void {
  if (commandId) pendingDraftCommands.set(key, commandId);
  else pendingDraftCommands.delete(key);
  try {
    const storageKey = `${DRAFT_COMMAND_PREFIX}${key}`;
    if (commandId) globalThis.localStorage?.setItem(storageKey, commandId);
    else globalThis.localStorage?.removeItem(storageKey);
  } catch {
    // The server remains authoritative; storage only extends retry identity.
  }
}

/**
 * Assemble the biography draft from the corroborated voices. Throws on a
 * no-key / engine failure (the caller shows AIActionFailure) — there is no
 * fabricated-biography path.
 */
async function executeDraftCommand(
  id: string,
  isPublic: boolean,
  logicalCommand: string,
): Promise<AssembledDraft> {
  const commandId = draftCommand(logicalCommand);
  persistDraftCommand(logicalCommand, commandId);
  const resp = await apiFetch(`/speak/projects/${encodeURIComponent(id)}/draft`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Idempotency-Key": commandId,
    },
    body: JSON.stringify({ public: isPublic }),
  });
  if (!resp.ok) {
    if (resp.status >= 400 && resp.status < 500) {
      persistDraftCommand(logicalCommand, null);
    }
    throw new Error(`HTTP ${resp.status}`);
  }
  const data = await resp.json();
  persistDraftCommand(logicalCommand, null);
  const excluded = Array.isArray(data.excluded_claim_ids) ? data.excluded_claim_ids.length : 0;
  return {
    deliverableId: typeof data.deliverable_id === "string" ? data.deliverable_id : "",
    prose: typeof data.prose_text === "string" ? data.prose_text : "",
    excludedCount: excluded,
  };
}

export function assembleDraft(id: string, isPublic: boolean): Promise<AssembledDraft> {
  const logicalCommand = JSON.stringify([id, isPublic]);
  const existing = inFlightDrafts.get(logicalCommand);
  if (existing) return existing;
  const request = executeDraftCommand(id, isPublic, logicalCommand).finally(() => {
    inFlightDrafts.delete(logicalCommand);
  });
  inFlightDrafts.set(logicalCommand, request);
  return request;
}

export interface SpeakPublication {
  served: boolean;
  documentId: string | null;
}

const pendingPublishCommands = new Map<string, string>();
const inFlightPublishes = new Map<string, Promise<SpeakPublication>>();
const PUBLISH_COMMAND_PREFIX = "antiek:speak-publish:";

function publishCommand(key: string): string {
  const inMemory = pendingPublishCommands.get(key);
  if (inMemory) return inMemory;
  try {
    const stored = globalThis.localStorage?.getItem(`${PUBLISH_COMMAND_PREFIX}${key}`);
    if (stored) return stored;
  } catch {
    // Same-tab memory remains available when persistent storage is restricted.
  }
  return crypto.randomUUID();
}

function persistPublishCommand(key: string, commandId: string | null): void {
  if (commandId) pendingPublishCommands.set(key, commandId);
  else pendingPublishCommands.delete(key);
  try {
    const storageKey = `${PUBLISH_COMMAND_PREFIX}${key}`;
    if (commandId) globalThis.localStorage?.setItem(storageKey, commandId);
    else globalThis.localStorage?.removeItem(storageKey);
  } catch {
    // Persistence improves transport recovery; the receipt remains authoritative.
  }
}

async function executePublishCommand(
  id: string,
  deliverableId: string,
  logicalCommand: string,
): Promise<SpeakPublication> {
  const commandId = publishCommand(logicalCommand);
  persistPublishCommand(logicalCommand, commandId);
  const resp = await apiFetch(`/speak/projects/${encodeURIComponent(id)}/publish`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Idempotency-Key": commandId,
    },
    body: JSON.stringify({ deliverable_id: deliverableId }),
  });
  if (!resp.ok) {
    if (resp.status >= 400 && resp.status < 500) persistPublishCommand(logicalCommand, null);
    let detail = `HTTP ${resp.status}`;
    try {
      const body = await resp.json();
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      // Preserve the status fallback for non-JSON failures.
    }
    throw new Error(detail);
  }
  const data = await resp.json();
  persistPublishCommand(logicalCommand, null);
  return {
    served: Boolean(data.served),
    documentId: typeof data.document_id === "string" ? data.document_id : null,
  };
}

/** Publish one assembled story exactly once across retries and browser reloads. */
export function publishProject(id: string, deliverableId: string): Promise<SpeakPublication> {
  const logicalCommand = JSON.stringify([id, deliverableId]);
  const existing = inFlightPublishes.get(logicalCommand);
  if (existing) return existing;
  const request = executePublishCommand(id, deliverableId, logicalCommand).finally(() => {
    inFlightPublishes.delete(logicalCommand);
  });
  inFlightPublishes.set(logicalCommand, request);
  return request;
}

/**
 * The browsable PUBLIC feed (M1) — only projects whose intent is public.
 * Distinct from `listPeople` (the operator's private dashboard of everyone
 * they're remembering). Honest when empty (returns []).
 */
export async function listPublicFeed(): Promise<FeedItem[]> {
  const resp = await apiFetch("/speak/feed");
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  const data = await resp.json();
  const rows: Record<string, unknown>[] = Array.isArray(data.projects) ? data.projects : [];
  return rows.map((r) => ({
    id: String(r.project_id ?? ""),
    name:
      typeof r.subject_ref === "string" && r.subject_ref
        ? r.subject_ref
        : typeof r.title === "string"
        ? r.title
        : "",
    voiceCount: typeof r.interview_count === "number" ? r.interview_count : 0,
    readerDocumentId: typeof r.document_id === "string" ? r.document_id : null,
  }));
}

export interface PayoutReleaseView {
  spentUsd: string;
  budgetUsd: string;
  budgetExhausted: boolean;
  cappedCount: number;
}

/**
 * Release graded payout for a project (M3) — routed through §9 into ESCROW.
 * Never disburses money (disbursement stays gated on G2/G3). Returns the
 * honest accrued figure (which is $0 with no ad buyers) and whether the
 * requester's budget was exhausted.
 */
// PAYOUT-BASIS GUARD: payout basis is §9.3 Option-B (claim_confidence × (6 − source_tier)); the per-second ad model is rejected. See docs/decisions/speak-private-public-spine.md.
export async function releasePayout(
  projectId: string,
  args: { informationGoal: string; budgetUsd: string; perInterviewCapUsd: string; adRevenueUsd: string },
): Promise<PayoutReleaseView> {
  const resp = await apiFetch(`/speak/projects/${encodeURIComponent(projectId)}/release-payout`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      information_goal: args.informationGoal,
      budget_usd: args.budgetUsd,
      per_interview_cap_usd: args.perInterviewCapUsd,
      ad_revenue_usd: args.adRevenueUsd,
    }),
  });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  const data = await resp.json();
  return {
    spentUsd: typeof data.spent_usd === "string" ? data.spent_usd : "0",
    budgetUsd: typeof data.budget_usd === "string" ? data.budget_usd : "0",
    budgetExhausted: Boolean(data.budget_exhausted),
    cappedCount: Array.isArray(data.capped_interview_ids) ? data.capped_interview_ids.length : 0,
  };
}

/**
 * SPR-11 — the Biography template composition over the ONE graph.
 *
 * A biography is a TEMPLATE composing Research + Write + Speak, NOT a fifth
 * product or a fifth graph. The three ids it wires together all resolve to one
 * shared identity (the investigationId): the Write deliverable's research link
 * == the investigationId, and the Speak project is linked via the shared
 * composition event. There is no biographyId — a biography is the composition,
 * not its own entity.
 */
export interface BiographyComposition {
  investigationId: string;
  deliverableId: string;
  projectId: string;
}

/**
 * Provision a biography: a Research folder (created first via
 * startInvestigation), then the Write deliverable scaffold + Speak interview
 * project wired to that same Research folder over the shared substrate. The
 * Research folder can be empty (no research run yet) and the Speak project
 * empty (no voices yet) — both provision regardless (rigor #3 edge cases a/c).
 */
export async function createBiography(args: {
  investigationId: string;
  subjectName: string;
  title?: string;
}): Promise<BiographyComposition> {
  const resp = await apiFetch("/speak/biography", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      investigation_id: args.investigationId,
      subject_name: args.subjectName.trim(),
      title: args.title,
    }),
  });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  const data = await resp.json();
  return {
    investigationId: String(data.investigation_id ?? ""),
    deliverableId: String(data.deliverable_id ?? ""),
    projectId: String(data.project_id ?? ""),
  };
}

export async function createPerson(name: string): Promise<string> {
  const trimmed = name.trim();
  const resp = await apiFetch("/speak/projects", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      title: `${trimmed}'s story`,
      subject_ref: trimmed,
      subject_status: "unknown",
      publish_intent: "private_never_published",
    }),
  });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  const data = await resp.json();
  if (!data.project_id) throw new Error("no project returned");
  return String(data.project_id);
}
