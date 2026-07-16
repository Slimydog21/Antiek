import { useCallback, useEffect, useState } from "react";

import SessionBrandChrome from "../../brand/SessionBrandChrome";
import { apiFetch } from "../../lib/api";

/**
 * Federation config UI (master-spec §13.9 Phase 3).
 *
 * Operator-facing surface for the substrate-wide federation policy.
 * Reads/writes /cross-graph/federation-config. The strict default
 * (no partners, opt-in + attribution required) is the starting
 * posture; this page is how the operator deviates from it.
 *
 * Partner-substrate IDs are validated server-side against
 * [a-zA-Z0-9_-]+ for path safety; the UI surfaces the 422 message
 * verbatim so the operator can correct.
 */

interface FederationConfig {
  allowed_partner_substrates: string[];
  require_opt_in_for_outbound_citations: boolean;
  require_attribution_for_outbound_citations: boolean;
}

export default function Federation() {
  const [config, setConfig] = useState<FederationConfig | null>(null);
  const [draft, setDraft] = useState<FederationConfig | null>(null);
  const [partnerInput, setPartnerInput] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState<boolean>(false);

  const reload = useCallback(async () => {
    setError(null);
    try {
      const resp = await apiFetch("/cross-graph/federation-config");
      if (!resp.ok) {
        throw new Error(`GET federation-config: HTTP ${resp.status}`);
      }
      const data: FederationConfig = await resp.json();
      setConfig(data);
      setDraft(data);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  const save = async () => {
    if (!draft || submitting) return;
    setSubmitting(true);
    setError(null);
    setSavedAt(null);
    try {
      const resp = await apiFetch("/cross-graph/federation-config", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(draft),
      });
      if (!resp.ok) {
        const errorBody = await resp.json().catch(() => null);
        const detail =
          errorBody?.detail?.message ?? `PUT failed: HTTP ${resp.status}`;
        throw new Error(detail);
      }
      const updated: FederationConfig = await resp.json();
      setConfig(updated);
      setDraft(updated);
      setSavedAt(new Date().toISOString());
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSubmitting(false);
    }
  };

  const addPartner = () => {
    if (!draft) return;
    const next = partnerInput.trim();
    if (!next) return;
    if (draft.allowed_partner_substrates.includes(next)) return;
    setDraft({
      ...draft,
      allowed_partner_substrates: [...draft.allowed_partner_substrates, next],
    });
    setPartnerInput("");
  };

  const removePartner = (id: string) => {
    if (!draft) return;
    setDraft({
      ...draft,
      allowed_partner_substrates: draft.allowed_partner_substrates.filter(
        (p) => p !== id,
      ),
    });
  };

  const isDirty =
    !!config &&
    !!draft &&
    (JSON.stringify(config.allowed_partner_substrates) !==
      JSON.stringify(draft.allowed_partner_substrates) ||
      config.require_opt_in_for_outbound_citations !==
        draft.require_opt_in_for_outbound_citations ||
      config.require_attribution_for_outbound_citations !==
        draft.require_attribution_for_outbound_citations);

  return (
    <div className="flex flex-col h-screen">
      <main className="flex-1 overflow-y-auto bg-ice-0 dark:bg-charcoal-2">
        <div className="max-w-3xl mx-auto px-8 py-10 space-y-6">
          <SessionBrandChrome
            testIdPrefix="federation-home"
            title="Federation config"
          >
            <p className="text-sm text-ink-soft dark:text-starlight leading-relaxed">
              Substrate-wide cross-graph federation policy (master-spec
              §13.9 Phase 3). Default is strict: no partners, opt-in
              and attribution required. Adding a partner here authorizes
              outbound citations to that partner&rsquo;s substrate; the
              attribution + rev-share path picks up the federated_substrate_id
              automatically.
            </p>
          </SessionBrandChrome>

          {error && (
            <p className="text-sm text-emperor border border-red-200 bg-red-50 px-3 py-2 rounded">
              {error}
            </p>
          )}

          {savedAt && !error && (
            <p className="text-sm text-emerald-700 border border-emerald-200 bg-emerald-50 px-3 py-2 rounded">
              Saved at {savedAt}
            </p>
          )}

          {draft && (
            <>
              <section className="border border-rule dark:border-charcoal-1 rounded-md p-5 space-y-3">
                <h2 className="text-base font-serif text-ink dark:text-bright">
                  Allowed partner substrates
                </h2>
                <p className="text-xs text-ink-soft dark:text-starlight">
                  Each id must match{" "}
                  <code className="font-mono">[a-zA-Z0-9_-]+</code>{" "}
                  (path-safe). Server validates on PUT.
                </p>

                {draft.allowed_partner_substrates.length === 0 ? (
                  <p className="text-sm italic text-shadow-1 dark:text-moonlight">
                    No partners yet. Adding the first one transitions
                    the substrate out of strict-default mode.
                  </p>
                ) : (
                  <ul className="space-y-1">
                    {draft.allowed_partner_substrates.map((p) => (
                      <li
                        key={p}
                        className="flex items-center justify-between gap-2 py-1 border-b border-rule dark:border-charcoal-1"
                      >
                        <code className="text-sm font-mono text-ink dark:text-bright">
                          {p}
                        </code>
                        <button
                          type="button"
                          onClick={() => removePartner(p)}
                          className="text-[10px] uppercase tracking-wider font-mono text-emperor hover:bg-red-50 px-1.5 py-0.5 rounded"
                        >
                          remove
                        </button>
                      </li>
                    ))}
                  </ul>
                )}

                <div className="flex gap-2 pt-2">
                  <input
                    type="text"
                    value={partnerInput}
                    onChange={(e) => setPartnerInput(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        e.preventDefault();
                        addPartner();
                      }
                    }}
                    placeholder="e.g. partner-research-coop"
                    className="flex-1 text-sm font-mono text-ink dark:text-bright border border-rule dark:border-charcoal-1 rounded p-2"
                  />
                  <button
                    type="button"
                    onClick={addPartner}
                    disabled={!partnerInput.trim()}
                    className="px-3 py-1.5 rounded-md bg-ink text-white text-xs font-medium hover:bg-shadow-2 transition-colors disabled:opacity-50"
                  >
                    Add
                  </button>
                </div>
              </section>

              <section className="border border-rule dark:border-charcoal-1 rounded-md p-5 space-y-3">
                <h2 className="text-base font-serif text-ink dark:text-bright">
                  Cross-graph discipline
                </h2>
                <label className="flex items-start gap-3 text-sm text-ink dark:text-bright">
                  <input
                    type="checkbox"
                    checked={draft.require_opt_in_for_outbound_citations}
                    onChange={(e) =>
                      setDraft({
                        ...draft,
                        require_opt_in_for_outbound_citations: e.target.checked,
                      })
                    }
                    className="mt-0.5 accent-ink dark:accent-bright"
                  />
                  <span>
                    <strong>Require opt-in for outbound citations.</strong>{" "}
                    A user's note can't be cited from another substrate
                    unless they explicitly opt in. Strict default; only
                    flip after explicit policy review.
                  </span>
                </label>
                <label className="flex items-start gap-3 text-sm text-ink dark:text-bright">
                  <input
                    type="checkbox"
                    checked={draft.require_attribution_for_outbound_citations}
                    onChange={(e) =>
                      setDraft({
                        ...draft,
                        require_attribution_for_outbound_citations:
                          e.target.checked,
                      })
                    }
                    className="mt-0.5 accent-ink dark:accent-bright"
                  />
                  <span>
                    <strong>Require attribution for outbound citations.</strong>{" "}
                    Federated citations must carry the originating
                    user_id so the §13.9 attribution + rev-share path
                    can route revenue back. Strict default.
                  </span>
                </label>
              </section>

              <section className="flex items-center justify-between">
                <p className="text-xs font-mono text-shadow-1 dark:text-moonlight">
                  {isDirty ? "unsaved changes" : "in sync with substrate"}
                </p>
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => void reload()}
                    disabled={submitting}
                    className="px-3 py-1.5 rounded-md border border-rule dark:border-charcoal-1 text-ink dark:text-bright text-xs font-medium hover:bg-ice-1 dark:bg-charcoal-2 transition-colors disabled:opacity-50"
                  >
                    Discard
                  </button>
                  <button
                    type="button"
                    onClick={() => void save()}
                    disabled={submitting || !isDirty}
                    className="px-3 py-1.5 rounded-md bg-ink text-white text-xs font-medium hover:bg-shadow-2 transition-colors disabled:opacity-50"
                  >
                    {submitting ? "Saving…" : "Save"}
                  </button>
                </div>
              </section>
            </>
          )}
        </div>
      </main>
    </div>
  );
}
