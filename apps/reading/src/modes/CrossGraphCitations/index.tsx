import { useCallback, useState } from "react";
import { Link } from "react-router-dom";

import citationEnvironment from "../../brand/werner/citations/citation_attribution_switchyard_environment_v1.webp";
import { apiFetch } from "../../lib/api";
import "./citation-attribution-switchyard.css";

export interface CitationDraft {
  referencing_user_id: string;
  referencing_investigation_id: string;
  referenced_user_id: string;
  referenced_note_id: string;
  federated_substrate_id?: string;
}

export interface RecordedCitation extends Omit<CitationDraft, "federated_substrate_id"> {
  reference_id: string;
  federated_substrate_id: string | null;
  cited_at: string;
}

export interface CrossGraphCitationsProps {
  recordCitation?: (draft: CitationDraft) => Promise<RecordedCitation>;
  executionEnabled?: boolean;
  initialRecorded?: RecordedCitation[];
  submittingPreview?: boolean;
  initialFederation?: boolean;
}

async function recordCitationToApi(draft: CitationDraft): Promise<RecordedCitation> {
  const response = await apiFetch("/cross-graph/citations", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(draft),
  });
  if (!response.ok) throw new Error("Citation recording failed");
  return response.json() as Promise<RecordedCitation>;
}

const SAFE_ERROR = "Could not record the citation reference. No reference was added.";

export default function CrossGraphCitations({
  recordCitation = recordCitationToApi,
  executionEnabled = true,
  initialRecorded = [],
  submittingPreview = false,
  initialFederation = false,
}: CrossGraphCitationsProps) {
  const [referencingUserId, setReferencingUserId] = useState("__operator__");
  const [referencingInvId, setReferencingInvId] = useState(initialFederation ? "inv-atlas" : "");
  const [referencedUserId, setReferencedUserId] = useState(initialFederation ? "research-partner" : "");
  const [referencedNoteId, setReferencedNoteId] = useState(initialFederation ? "note-fieldwork" : "");
  const [federationToggle, setFederationToggle] = useState(initialFederation);
  const [federatedSubstrateId, setFederatedSubstrateId] = useState(initialFederation ? "partner-research-coop" : "");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [recorded, setRecorded] = useState(initialRecorded);

  const isSubmitting = submitting || submittingPreview;
  const canSubmit = Boolean(
    executionEnabled && referencingUserId.trim() && referencingInvId.trim() &&
      referencedUserId.trim() && referencedNoteId.trim() &&
      (!federationToggle || federatedSubstrateId.trim()),
  );

  const submit = useCallback(async () => {
    if (!canSubmit || isSubmitting) return;
    setSubmitting(true);
    setError(null);
    const draft: CitationDraft = {
      referencing_user_id: referencingUserId.trim(),
      referencing_investigation_id: referencingInvId.trim(),
      referenced_user_id: referencedUserId.trim(),
      referenced_note_id: referencedNoteId.trim(),
    };
    if (federationToggle) draft.federated_substrate_id = federatedSubstrateId.trim();
    try {
      const created = await recordCitation(draft);
      setRecorded((previous) => [created, ...previous]);
      setReferencedUserId("");
      setReferencedNoteId("");
    } catch {
      setError(SAFE_ERROR);
    } finally {
      setSubmitting(false);
    }
  }, [canSubmit, isSubmitting, referencingUserId, referencingInvId, referencedUserId, referencedNoteId, federationToggle, federatedSubstrateId, recordCitation]);

  return (
    <main className="citation-switchyard" data-theme-preview={submittingPreview ? "submitting" : undefined}>
      <img className="citation-switchyard__environment" src={citationEnvironment} alt="" aria-hidden="true" draggable={false} />
      <div className="citation-switchyard__veil" aria-hidden="true" />
      <div className="citation-switchyard__shell">
        <header className="citation-switchyard__header">
          <p className="citation-switchyard__eyebrow">Knowledge graph · reference desk</p>
          <h1>Citation attribution switchyard</h1>
          <p className="citation-switchyard__lede">Records a citation reference between an investigation and a public note.</p>
          <div className="citation-switchyard__truth" role="note">
            <strong>Reference, not clearance.</strong> This screen does not verify partner trust or consent and does not execute a payout. Attribution and any revenue handling happen downstream under separate policy.
          </div>
        </header>

        {error && <p className="citation-switchyard__alert" role="alert">{error}</p>}

        <section className="citation-switchyard__panel" aria-labelledby="citation-route-title">
          <div className="citation-switchyard__section-heading">
            <div><p className="citation-switchyard__kicker">New reference</p><h2 id="citation-route-title">Set the citation route</h2></div>
            <span className="citation-switchyard__status">Draft · not recorded</span>
          </div>

          <div className="citation-switchyard__route">
            <fieldset className="citation-switchyard__terminal">
              <legend>From · operator context</legend>
              <Field id="referencing-user" label="Operator identity">
                <input id="referencing-user" value={referencingUserId} onChange={(event) => setReferencingUserId(event.target.value)} required />
              </Field>
              <Field id="referencing-investigation" label="Investigation">
                <input id="referencing-investigation" value={referencingInvId} onChange={(event) => setReferencingInvId(event.target.value)} placeholder="inv-…" required />
              </Field>
            </fieldset>
            <div className="citation-switchyard__conduit" aria-hidden="true"><span>reference</span></div>
            <fieldset className="citation-switchyard__terminal">
              <legend>To · cited work</legend>
              <Field id="referenced-user" label="Referenced contributor">
                <input id="referenced-user" value={referencedUserId} onChange={(event) => setReferencedUserId(event.target.value)} placeholder="user-…" required />
              </Field>
              <Field id="referenced-note" label="Public note">
                <input id="referenced-note" value={referencedNoteId} onChange={(event) => setReferencedNoteId(event.target.value)} placeholder="note-…" required />
              </Field>
            </fieldset>
          </div>

          <div className="citation-switchyard__federation">
            <label className="citation-switchyard__check"><input type="checkbox" checked={federationToggle} onChange={(event) => setFederationToggle(event.target.checked)} /><span><strong>Partner substrate reference</strong><small>Add the partner substrate identifier to this reference.</small></span></label>
            {federationToggle && <><Field id="federated-substrate" label="Partner substrate identifier"><input id="federated-substrate" value={federatedSubstrateId} onChange={(event) => setFederatedSubstrateId(event.target.value)} placeholder="partner-…" required /></Field><p className="citation-switchyard__policy">This does not verify trust, allow-list status, or consent. Review the <Link to="/federation">federation policy</Link> first.</p></>}
          </div>

          <div className="citation-switchyard__actions">
            <p>Only the reference is written here. Downstream systems may consume it under their own authority.</p>
            <button type="button" onClick={() => void submit()} disabled={!canSubmit || isSubmitting}>{isSubmitting ? "Recording reference…" : "Record reference"}</button>
          </div>
        </section>

        <section className="citation-switchyard__receipts" aria-labelledby="citation-receipts-title">
          <div className="citation-switchyard__section-heading"><div><p className="citation-switchyard__kicker">This session</p><h2 id="citation-receipts-title">Reference receipts</h2></div><span className="citation-switchyard__status">Not durable history</span></div>
          <p className="citation-switchyard__receipt-note">Receipts shown here last for this session only.</p>
          <div aria-live="polite" aria-atomic="true" className="citation-switchyard__live">{recorded.length === 0 ? "No references recorded in this session." : `${recorded.length} reference${recorded.length === 1 ? "" : "s"} recorded in this session.`}</div>
          {recorded.length > 0 && <ol className="citation-switchyard__receipt-list">{recorded.map((citation) => <li key={citation.reference_id}><div><strong>{citation.referencing_investigation_id}</strong><span aria-hidden="true">→</span><strong>{citation.referenced_note_id}</strong></div><p>{citation.reference_id} · {citation.federated_substrate_id ? `partner ${citation.federated_substrate_id}` : "same substrate"} · {citation.cited_at}</p></li>)}</ol>}
        </section>
      </div>
    </main>
  );
}

function Field({ id, label, children }: { id: string; label: string; children: React.ReactNode }) {
  return <div className="citation-switchyard__field"><label htmlFor={id}>{label}</label>{children}</div>;
}
