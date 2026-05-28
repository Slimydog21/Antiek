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
  const excluded = Array.isArray(data.excluded_claim_ids) ? data.excluded_claim_ids.length : 0;
  return { prose: typeof data.prose_text === "string" ? data.prose_text : "", excludedCount: excluded };
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
