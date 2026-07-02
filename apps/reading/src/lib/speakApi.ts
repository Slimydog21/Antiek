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
import { requireInvestigationId } from "./investigationData";

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
}

const VOICE_STATE: Record<string, VoiceState> = {
  invited: "invited",
  in_progress: "recording",
  completed: "shared",
  declined: "declined",
  incomplete: "unfinished",
};

function record(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function objectRecord(value: unknown): Record<string, unknown> {
  return record(value) ?? {};
}

function nonEmptyString(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

function nonNegativeSafeInteger(value: unknown): number | null {
  const parsed =
    typeof value === "number"
      ? value
      : typeof value === "string" && value.trim() !== ""
        ? Number(value)
        : Number.NaN;
  return Number.isSafeInteger(parsed) && parsed >= 0 ? parsed : null;
}

function stringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) => {
    const text = nonEmptyString(item);
    return text ? [text] : [];
  });
}

export function requireNonEmptyField(value: unknown, field: string): string {
  const trimmed = nonEmptyString(value);
  if (!trimmed) {
    throw new TypeError(`${field} must be a non-empty string`);
  }
  return trimmed;
}

export function toPerson(raw: Record<string, unknown>): RememberedPerson {
  const subject = nonEmptyString(raw.subject_ref);
  const title = nonEmptyString(raw.title) ?? "Untitled story";
  const publish = nonEmptyString(raw.publish_intent) ?? "";
  return {
    id: requireNonEmptyField(raw.project_id, "project_id"),
    name: subject ?? title,
    willBePublic: publish === "will_be_public",
    voiceCount: nonNegativeSafeInteger(raw.interview_count) ?? 0,
  };
}

export function toProjectDetail(raw: Record<string, unknown>): ProjectDetail {
  const subject = nonEmptyString(raw.subject_ref);
  const title = nonEmptyString(raw.title) ?? "Untitled story";
  const publish = nonEmptyString(raw.publish_intent) ?? "";
  const status = nonEmptyString(raw.subject_status) ?? "";
  return {
    id: requireNonEmptyField(raw.project_id, "project_id"),
    name: subject ?? title,
    willBePublic: publish === "will_be_public",
    subjectStatusWord:
      status && status !== "unknown" ? status.replace(/_/g, " ") : null,
  };
}

export function toEconomics(raw: Record<string, unknown>): EconomicsView {
  return {
    splitApplies: raw.split_applies === true,
    creatorCarriesCost: raw.creator_carries_cost === true,
    // Read-only gate state. The backend denies by default; the UI shows
    // these gated and never offers a way to close them.
    publicPublishingAllowed: raw.public_publishing_allowed === true,
    publicPublishingReason: nonEmptyString(raw.public_publishing_reason) ?? "",
    disbursementAllowed: raw.disbursement_allowed === true,
    disbursementReason: nonEmptyString(raw.disbursement_reason) ?? "",
  };
}

export function toVoice(raw: Record<string, unknown>): ArrivingVoice {
  const email = nonEmptyString(raw.informant_email);
  const handle = nonEmptyString(raw.informant_handle);
  const status = nonEmptyString(raw.status) ?? "invited";
  return {
    interviewId: requireNonEmptyField(raw.interview_id, "interview_id"),
    who: email ?? handle ?? "Someone you invited",
    state: VOICE_STATE[status] ?? "invited",
    link: nonEmptyString(raw.link) ?? "",
  };
}

/** Cluster `label` → the honest agreement vocabulary. NEVER returns "proven". */
export function toAgreementKind(label: string): AgreementPoint["kind"] {
  if (label === "multiply_attested") return "corroborated";
  if (label === "contradicted") return "disagreement";
  return "single";
}

function toAgreementPoint(raw: Record<string, unknown>): AgreementPoint | null {
  const label = nonEmptyString(raw.label) ?? "";
  const text =
    nonEmptyString(raw.canonical_text) ??
    (label ? label.replace(/_/g, " ") : null);
  if (!text) return null;
  return {
    text,
    kind: toAgreementKind(label),
    voices: nonNegativeSafeInteger(raw.independent_attesters) ?? 1,
  };
}

// ── calls ──────────────────────────────────────────────────────────────

export async function listPeople(): Promise<RememberedPerson[]> {
  const resp = await apiFetch("/speak/projects");
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  const data = await resp.json();
  const body = record(data);
  const rows = Array.isArray(body?.projects) ? body.projects : [];
  return rows.flatMap((row) => {
    try {
      const item = record(row);
      return item ? [toPerson(item)] : [];
    } catch {
      return [];
    }
  });
}

export async function getProject(id: string): Promise<ProjectDetail> {
  const resp = await apiFetch(`/speak/projects/${encodeURIComponent(id)}`);
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return toProjectDetail(objectRecord(await resp.json()));
}

export async function getEconomics(id: string): Promise<EconomicsView> {
  const resp = await apiFetch(`/speak/projects/${encodeURIComponent(id)}/economics`);
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return toEconomics(objectRecord(await resp.json()));
}

export async function listVoices(id: string): Promise<ArrivingVoice[]> {
  const resp = await apiFetch(`/speak/projects/${encodeURIComponent(id)}/invites`);
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  const data = await resp.json();
  const body = record(data);
  const rows = Array.isArray(body?.invites) ? body.invites : [];
  return rows.flatMap((row) => {
    try {
      const item = record(row);
      return item ? [toVoice(item)] : [];
    } catch {
      return [];
    }
  });
}

export async function inviteByEmail(id: string, email: string): Promise<ArrivingVoice> {
  const resp = await apiFetch(`/speak/projects/${encodeURIComponent(id)}/invites`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ informant_email: email }),
  });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return toVoice(objectRecord(await resp.json()));
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
  return requireNonEmptyField(toVoice(objectRecord(await resp.json())).link, "link");
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
  const body = record(data);
  const clusters = Array.isArray(body?.clusters) ? body.clusters : [];
  return clusters.flatMap((cluster) => {
    const item = record(cluster);
    const point = item ? toAgreementPoint(item) : null;
    return point ? [point] : [];
  });
}

export interface AssembledDraft {
  prose: string;
  /** Points left out because they aren't corroborated / are contradicted. */
  excludedCount: number;
}

/**
 * Assemble the biography draft from the corroborated voices. Throws on a
 * no-key / engine failure (the caller shows AIActionFailure) — there is no
 * fabricated-biography path.
 */
export async function assembleDraft(id: string, isPublic: boolean): Promise<AssembledDraft> {
  const resp = await apiFetch(`/speak/projects/${encodeURIComponent(id)}/draft`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ public: isPublic }),
  });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  const data = await resp.json();
  const body = record(data);
  return {
    prose: nonEmptyString(body?.prose_text) ?? "",
    excludedCount: stringArray(body?.excluded_claim_ids).length,
  };
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
  const body = record(data);
  const rows = Array.isArray(body?.projects) ? body.projects : [];
  return rows.flatMap((r) => {
    try {
      const row = record(r);
      if (!row) return [];
      return [
        {
          id: requireNonEmptyField(row.project_id, "project_id"),
          name:
            nonEmptyString(row.subject_ref) ??
            nonEmptyString(row.title) ??
            "Untitled story",
          voiceCount: nonNegativeSafeInteger(row.interview_count) ?? 0,
        },
      ];
    } catch {
      return [];
    }
  });
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
  const body = record(data);
  return {
    spentUsd: nonEmptyString(body?.spent_usd) ?? "0",
    budgetUsd: nonEmptyString(body?.budget_usd) ?? "0",
    budgetExhausted: body?.budget_exhausted === true,
    cappedCount: stringArray(body?.capped_interview_ids).length,
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
  const data = objectRecord(await resp.json());
  return {
    investigationId: requireInvestigationId(data.investigation_id),
    deliverableId: requireNonEmptyField(data.deliverable_id, "deliverable_id"),
    projectId: requireNonEmptyField(data.project_id, "project_id"),
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
  const data = objectRecord(await resp.json());
  return requireNonEmptyField(data.project_id, "project_id");
}
