import { useCallback, useState } from "react";
import { Link } from "react-router-dom";

import SessionBrandChrome from "../../brand/SessionBrandChrome";
import { apiFetch } from "../../lib/api";

/**
 * Cross-graph citation recording UI (master-spec §13.9 Phase 3).
 *
 * Operator-facing form for ``POST /cross-graph/citations``.
 * Records a citation from one user's investigation to another
 * user's public note. The attribution pipeline picks up the
 * recorded reference and routes 70% of any attached ad revenue
 * to the referenced user via the existing Stripe Connect path.
 *
 * For federation citations (citing a partner substrate's content),
 * the operator must have the partner substrate's id authorized in
 * /federation first; the form surfaces the relationship explicitly
 * so the operator can't accidentally route revenue to an
 * un-allow-listed substrate.
 */

interface RecordedCitation {
  reference_id: string;
  referencing_user_id: string;
  referencing_investigation_id: string;
  referenced_user_id: string;
  referenced_note_id: string;
  federated_substrate_id: string | null;
  cited_at: string;
}

export default function CrossGraphCitations() {
  const [referencingUserId, setReferencingUserId] = useState<string>("__operator__");
  const [referencingInvId, setReferencingInvId] = useState<string>("");
  const [referencedUserId, setReferencedUserId] = useState<string>("");
  const [referencedNoteId, setReferencedNoteId] = useState<string>("");
  const [federationToggle, setFederationToggle] = useState<boolean>(false);
  const [federatedSubstrateId, setFederatedSubstrateId] = useState<string>("");
  const [submitting, setSubmitting] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [recorded, setRecorded] = useState<RecordedCitation[]>([]);

  const canSubmit =
    referencingUserId.trim() &&
    referencingInvId.trim() &&
    referencedUserId.trim() &&
    referencedNoteId.trim() &&
    (!federationToggle || federatedSubstrateId.trim());

  const submit = useCallback(async () => {
    if (!canSubmit || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const body: Record<string, unknown> = {
        referencing_user_id: referencingUserId.trim(),
        referencing_investigation_id: referencingInvId.trim(),
        referenced_user_id: referencedUserId.trim(),
        referenced_note_id: referencedNoteId.trim(),
      };
      if (federationToggle && federatedSubstrateId.trim()) {
        body.federated_substrate_id = federatedSubstrateId.trim();
      }
      const resp = await apiFetch("/cross-graph/citations", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!resp.ok) {
        const txt = await resp.text();
        throw new Error(
          `POST /cross-graph/citations: HTTP ${resp.status} — ${txt}`,
        );
      }
      const created: RecordedCitation = await resp.json();
      setRecorded((prev) => [created, ...prev]);
      setReferencedUserId("");
      setReferencedNoteId("");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSubmitting(false);
    }
  }, [
    canSubmit,
    submitting,
    referencingUserId,
    referencingInvId,
    referencedUserId,
    referencedNoteId,
    federationToggle,
    federatedSubstrateId,
  ]);

  return (
    <div className="flex flex-col h-screen">
      <main className="flex-1 overflow-y-auto bg-ice-0 dark:bg-charcoal-2">
        <div className="max-w-3xl mx-auto px-8 py-10 space-y-6">
          <SessionBrandChrome
            testIdPrefix="cross-graph-home"
            title="Cross-graph citations"
          >
            <p className="text-sm text-ink-soft dark:text-starlight leading-relaxed">
              Record a citation from one user&rsquo;s investigation to
              another user&rsquo;s public note. Per master-spec §13.9
              Phase 3: the attribution pipeline picks this up and
              routes 70% of any attached ad revenue to the
              referenced user.
            </p>
            <p className="text-xs font-mono text-shadow-1 dark:text-moonlight">
              For federation citations:{" "}
              <Link to="/federation" className="underline hover:text-ink dark:text-bright">
                /federation
              </Link>{" "}
              must allow-list the partner substrate first.
            </p>
          </SessionBrandChrome>

          {error && (
            <p className="text-sm text-emperor border border-red-200 bg-red-50 px-3 py-2 rounded">
              {error}
            </p>
          )}

          <section className="border border-rule dark:border-charcoal-1 rounded-md p-5 space-y-3">
            <h2 className="text-base font-serif text-ink dark:text-bright">
              Record citation
            </h2>
            <Row label="Referencing user_id" required>
              <input
                type="text"
                value={referencingUserId}
                onChange={(e) => setReferencingUserId(e.target.value)}
                className="w-full text-xs font-mono text-ink dark:text-bright border border-rule dark:border-charcoal-1 rounded p-2"
              />
            </Row>
            <Row label="Referencing investigation_id" required>
              <input
                type="text"
                value={referencingInvId}
                onChange={(e) => setReferencingInvId(e.target.value)}
                placeholder="inv-..."
                className="w-full text-xs font-mono text-ink dark:text-bright border border-rule dark:border-charcoal-1 rounded p-2"
              />
            </Row>
            <Row label="Referenced user_id" required>
              <input
                type="text"
                value={referencedUserId}
                onChange={(e) => setReferencedUserId(e.target.value)}
                placeholder="user-A"
                className="w-full text-xs font-mono text-ink dark:text-bright border border-rule dark:border-charcoal-1 rounded p-2"
              />
            </Row>
            <Row label="Referenced note_id" required>
              <input
                type="text"
                value={referencedNoteId}
                onChange={(e) => setReferencedNoteId(e.target.value)}
                placeholder="note-7"
                className="w-full text-xs font-mono text-ink dark:text-bright border border-rule dark:border-charcoal-1 rounded p-2"
              />
            </Row>
            <label className="flex items-center gap-2 text-sm text-ink dark:text-bright">
              <input
                type="checkbox"
                checked={federationToggle}
                onChange={(e) => setFederationToggle(e.target.checked)}
                className="accent-ink dark:accent-bright"
              />
              <span>This is a federation citation (cross-substrate)</span>
            </label>
            {federationToggle && (
              <Row label="Federated substrate id" required>
                <input
                  type="text"
                  value={federatedSubstrateId}
                  onChange={(e) => setFederatedSubstrateId(e.target.value)}
                  placeholder="partner-research-coop"
                  className="w-full text-xs font-mono text-ink dark:text-bright border border-rule dark:border-charcoal-1 rounded p-2"
                />
              </Row>
            )}
            <button
              type="button"
              onClick={() => void submit()}
              disabled={!canSubmit || submitting}
              className="px-3 py-1.5 rounded-md bg-ink text-white text-xs font-medium hover:bg-shadow-2 transition-colors disabled:opacity-50"
            >
              {submitting ? "Recording…" : "Record citation"}
            </button>
          </section>

          {recorded.length > 0 && (
            <section className="border border-rule dark:border-charcoal-1 rounded-md p-5 space-y-3">
              <h2 className="text-base font-serif text-ink dark:text-bright">
                Recently recorded
              </h2>
              <ul className="space-y-2">
                {recorded.map((c) => (
                  <li
                    key={c.reference_id}
                    className="border border-rule dark:border-charcoal-1 rounded-md px-3 py-2"
                  >
                    <p className="text-xs font-mono text-ink dark:text-bright truncate">
                      {c.referencing_user_id}/{c.referencing_investigation_id}{" "}
                      → {c.referenced_user_id}/{c.referenced_note_id}
                    </p>
                    <p className="text-[11px] font-mono text-shadow-1 dark:text-moonlight">
                      {c.reference_id} · {c.cited_at}
                      {c.federated_substrate_id ? (
                        <> · federated: {c.federated_substrate_id}</>
                      ) : (
                        <> · same-substrate</>
                      )}
                    </p>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>
      </main>
    </div>
  );
}

function Row({
  label,
  required,
  children,
}: { label: string; required?: boolean; children: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <label className="text-[10px] font-mono uppercase text-shadow-1 dark:text-moonlight">
        {label}
        {required && <span className="text-emperor ml-0.5">*</span>}
      </label>
      {children}
    </div>
  );
}
