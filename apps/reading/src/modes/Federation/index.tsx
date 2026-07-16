import { FormEvent, useCallback, useEffect, useRef, useState } from "react";

import Werner from "../../brand/Werner";
import environment from "../../brand/werner/federation/federation_policy_airlock_environment_v1.webp";
import { apiFetch } from "../../lib/api";
import "./federation-policy-airlock.css";
import "./federation-policy-dialog.css";

export interface FederationConfig {
  allowed_partner_substrates: string[];
  require_opt_in_for_outbound_citations: boolean;
  require_attribution_for_outbound_citations: boolean;
}

export type FederationPolicyViewProps = {
  current: FederationConfig | null;
  draft: FederationConfig | null;
  state?: "ready" | "loading" | "saving" | "load-error" | "save-error";
  notice?: "saved" | null;
  confirmationOpen?: boolean;
  onDraftChange: (draft: FederationConfig) => void;
  onRequestSave: () => void;
  onConfirmSave: () => void;
  onCancelConfirm: () => void;
  onDiscard: () => void;
  onRetry: () => void;
};

const PARTNER_ID = /^[a-zA-Z0-9_-]+$/;
const safeConfig = (value: unknown): FederationConfig | null => {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const row = value as Record<string, unknown>;
  if (
    !Array.isArray(row.allowed_partner_substrates) ||
    !row.allowed_partner_substrates.every((id) => typeof id === "string" && PARTNER_ID.test(id)) ||
    typeof row.require_opt_in_for_outbound_citations !== "boolean" ||
    typeof row.require_attribution_for_outbound_citations !== "boolean"
  ) return null;
  if (new Set(row.allowed_partner_substrates).size !== row.allowed_partner_substrates.length) return null;
  return {
    allowed_partner_substrates: [...row.allowed_partner_substrates],
    require_opt_in_for_outbound_citations: row.require_opt_in_for_outbound_citations,
    require_attribution_for_outbound_citations: row.require_attribution_for_outbound_citations,
  };
};

const sameConfig = (a: FederationConfig | null, b: FederationConfig | null) =>
  Boolean(a && b) &&
  a!.require_opt_in_for_outbound_citations === b!.require_opt_in_for_outbound_citations &&
  a!.require_attribution_for_outbound_citations === b!.require_attribution_for_outbound_citations &&
  JSON.stringify([...a!.allowed_partner_substrates].sort()) === JSON.stringify([...b!.allowed_partner_substrates].sort());

const expandsRisk = (current: FederationConfig, draft: FederationConfig) =>
  draft.allowed_partner_substrates.some((id) => !current.allowed_partner_substrates.includes(id)) ||
  (current.require_opt_in_for_outbound_citations && !draft.require_opt_in_for_outbound_citations) ||
  (current.require_attribution_for_outbound_citations && !draft.require_attribution_for_outbound_citations);

export function FederationPolicyView({
  current, draft, state = "ready", notice = null, confirmationOpen = false,
  onDraftChange, onRequestSave, onConfirmSave, onCancelConfirm, onDiscard, onRetry,
}: FederationPolicyViewProps) {
  const [partnerInput, setPartnerInput] = useState("");
  const [inputError, setInputError] = useState<string | null>(null);
  const cancelConfirmRef = useRef<HTMLButtonElement>(null);
  const confirmRef = useRef<HTMLButtonElement>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);
  const dirty = !sameConfig(current, draft);
  const risky = Boolean(current && draft && expandsRisk(current, draft));
  useEffect(() => {
    if (!confirmationOpen) return;
    previousFocusRef.current = document.activeElement as HTMLElement | null;
    cancelConfirmRef.current?.focus();
    return () => previousFocusRef.current?.focus();
  }, [confirmationOpen]);
  const addPartner = (event: FormEvent) => {
    event.preventDefault();
    if (!draft) return;
    const id = partnerInput.trim();
    if (!PARTNER_ID.test(id)) {
      setInputError("Use letters, numbers, hyphens, or underscores only.");
      return;
    }
    if (draft.allowed_partner_substrates.includes(id)) {
      setInputError("That partner is already in the draft.");
      return;
    }
    onDraftChange({ ...draft, allowed_partner_substrates: [...draft.allowed_partner_substrates, id].sort() });
    setPartnerInput("");
    setInputError(null);
  };
  return (
    <main className="fpa-shell">
      <img className="fpa-environment" src={environment} alt="" aria-hidden="true" />
      <div className="fpa-veil" aria-hidden="true" />
      <div className="fpa-content">
        <header className="fpa-hero">
          <div><p className="fpa-eyebrow">Cross-substrate policy · operator airlock</p><h1>Federation Airlock</h1><p>Control which partner substrates may exchange citations with this installation, and preserve the consent and attribution gates applied to outbound work.</p></div>
          <Werner mood={state.endsWith("error") ? "empty" : state === "saving" ? "thinking" : "idle"} size={58} label="Werner monitors the policy airlock" />
        </header>

        <aside className="fpa-truth" aria-label="Policy boundary"><p className="fpa-eyebrow">What this policy establishes</p><p>The allow-list gates <strong>both outbound eligibility and inbound acceptance</strong>. It does not register a partner, prove trust, inspect content safety, grant legal clearance, or execute attribution or payouts. Partner identity and trust are separate controls.</p></aside>

        {state === "loading" && <section className="fpa-state" aria-live="polite"><h2>Reading the enforced policy…</h2><p>No policy is inferred while the substrate responds.</p></section>}
        {state === "load-error" && <section className="fpa-state fpa-state--error" role="alert"><h2>Policy unavailable</h2><p>The airlock could not verify the current substrate policy. No local draft was presented as enforced.</p><button type="button" onClick={onRetry}>Try again</button></section>}
        {state === "save-error" && <section className="fpa-state fpa-state--error" role="alert"><h2>Policy was not confirmed</h2><p>The substrate did not confirm this write. Your draft remains here for review; the previously read policy remains the enforced reference.</p><button type="button" onClick={onRequestSave}>Try saving again</button></section>}
        {notice === "saved" && !state.endsWith("error") && <p className="fpa-notice" role="status">Policy saved and read back from the substrate.</p>}

        {draft && current && <>
          <section className="fpa-board" aria-labelledby="partners-title">
            <header><div><p className="fpa-eyebrow">Gate 01 · bidirectional allow-list</p><h2 id="partners-title">Partner passages</h2></div><strong>{draft.allowed_partner_substrates.length}</strong></header>
            <p>Each identifier permits outbound federation attempts and inbound citation acceptance at the config layer. Separate registration and trusted status are still required.</p>
            {draft.allowed_partner_substrates.length ? <ul className="fpa-partners">{draft.allowed_partner_substrates.map((id) => <li key={id}><code>{id}</code><button type="button" onClick={() => onDraftChange({ ...draft, allowed_partner_substrates: draft.allowed_partner_substrates.filter((item) => item !== id) })} aria-label={`Remove ${id} from draft`}>Remove</button></li>)}</ul> : <p className="fpa-empty">No partner passages are allowed. This is the strict default.</p>}
            <form className="fpa-add" onSubmit={addPartner} noValidate><label htmlFor="federation-partner">Partner substrate identifier</label><div><input id="federation-partner" value={partnerInput} onChange={(event) => { setPartnerInput(event.target.value); setInputError(null); }} aria-describedby={inputError ? "partner-error" : "partner-hint"} aria-invalid={Boolean(inputError)} placeholder="partner-research-coop" /><button type="submit">Add to draft</button></div><small id="partner-hint">Letters, numbers, hyphens, and underscores.</small>{inputError && <small id="partner-error" role="alert">{inputError}</small>}</form>
          </section>

          <section className="fpa-board" aria-labelledby="discipline-title"><p className="fpa-eyebrow">Gate 02 · outbound discipline</p><h2 id="discipline-title">Consent and attribution</h2><p>These safeguards apply to outbound citations only. Inbound citation acceptance does not re-check them.</p>
            <label className="fpa-switch"><input type="checkbox" checked={draft.require_opt_in_for_outbound_citations} onChange={(event) => onDraftChange({ ...draft, require_opt_in_for_outbound_citations: event.target.checked })} /><span><strong>Require explicit opt-in</strong><small>Refuse outbound federation when the referenced user has not opted in.</small></span></label>
            <label className="fpa-switch"><input type="checkbox" checked={draft.require_attribution_for_outbound_citations} onChange={(event) => onDraftChange({ ...draft, require_attribution_for_outbound_citations: event.target.checked })} /><span><strong>Require attribution consent</strong><small>Refuse outbound federation when attribution metadata is not consented to.</small></span></label>
          </section>

          <section className="fpa-diff" aria-labelledby="review-title"><div><p className="fpa-eyebrow">Gate 03 · review</p><h2 id="review-title">{dirty ? "Draft differs from enforced policy" : "Draft matches enforced policy"}</h2><p>{risky ? "This draft expands passage or weakens an outbound safeguard. A second review is required." : dirty ? "This draft only narrows the current policy." : "Nothing will be written until the draft changes."}</p></div><div className="fpa-actions"><button type="button" className="fpa-secondary" onClick={onDiscard} disabled={!dirty || state === "saving"}>Discard draft</button><button type="button" onClick={onRequestSave} disabled={!dirty || state === "saving"}>{state === "saving" ? "Sealing policy…" : risky ? "Review expanded risk" : "Save narrower policy"}</button></div></section>

          {confirmationOpen && <><div className="fpa-scrim" aria-hidden="true" onMouseDown={onCancelConfirm} /><section className="fpa-confirm" role="dialog" aria-modal="true" aria-labelledby="confirm-title" onKeyDown={(event) => { if (event.key === "Escape") { event.preventDefault(); onCancelConfirm(); } if (event.key === "Tab") { if (event.shiftKey && document.activeElement === cancelConfirmRef.current) { event.preventDefault(); confirmRef.current?.focus(); } else if (!event.shiftKey && document.activeElement === confirmRef.current) { event.preventDefault(); cancelConfirmRef.current?.focus(); } } }}><p className="fpa-eyebrow">Second seal required</p><h2 id="confirm-title">Confirm the expanded policy boundary</h2><p>This change may admit inbound citations, permit outbound attempts, or remove a user safeguard. It still does not establish partner registration or trust.</p><div className="fpa-actions"><button ref={cancelConfirmRef} type="button" className="fpa-secondary" onClick={onCancelConfirm}>Keep reviewing</button><button ref={confirmRef} type="button" onClick={onConfirmSave}>Confirm and save</button></div></section></>}
        </>}
      </div>
    </main>
  );
}

export default function Federation() {
  const [current, setCurrent] = useState<FederationConfig | null>(null);
  const [draft, setDraft] = useState<FederationConfig | null>(null);
  const [state, setState] = useState<"ready" | "loading" | "saving" | "load-error" | "save-error">("loading");
  const [notice, setNotice] = useState<"saved" | null>(null);
  const [confirmationOpen, setConfirmationOpen] = useState(false);
  const requestRef = useRef(0);
  const load = useCallback(async () => {
    const token = ++requestRef.current;
    setState("loading"); setNotice(null); setConfirmationOpen(false);
    try {
      const response = await apiFetch("/cross-graph/federation-config");
      if (!response.ok) throw new Error("load");
      const parsed = safeConfig(await response.json());
      if (token !== requestRef.current) return;
      if (!parsed) throw new Error("shape");
      setCurrent(parsed); setDraft(parsed); setState("ready");
    } catch {
      if (token !== requestRef.current) return;
      setCurrent(null); setDraft(null); setState("load-error");
    }
  }, []);
  useEffect(() => { void load(); return () => { requestRef.current += 1; }; }, [load]);
  const save = useCallback(async () => {
    if (!draft || state === "saving") return;
    const token = ++requestRef.current;
    setState("saving"); setNotice(null); setConfirmationOpen(false);
    try {
      const response = await apiFetch("/cross-graph/federation-config", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(draft) });
      if (!response.ok) throw new Error("save");
      const parsed = safeConfig(await response.json());
      if (token !== requestRef.current) return;
      if (!parsed) throw new Error("shape");
      setCurrent(parsed); setDraft(parsed); setState("ready"); setNotice("saved");
    } catch {
      if (token !== requestRef.current) return;
      setState("save-error"); setNotice(null);
    }
  }, [draft, state]);
  const requestSave = () => {
    if (!current || !draft) return;
    if (expandsRisk(current, draft)) setConfirmationOpen(true); else void save();
  };
  return <FederationPolicyView current={current} draft={draft} state={state} notice={notice} confirmationOpen={confirmationOpen} onDraftChange={(next) => { setDraft(next); setNotice(null); setConfirmationOpen(false); }} onRequestSave={requestSave} onConfirmSave={() => void save()} onCancelConfirm={() => setConfirmationOpen(false)} onDiscard={() => { setDraft(current); setConfirmationOpen(false); setNotice(null); }} onRetry={() => void load()} />;
}
