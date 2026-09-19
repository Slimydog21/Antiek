import { useEffect, useMemo, useRef, useState } from "react";

import {
  approveCollectiveCouncil,
  convergeCollectiveCouncil,
  fetchCollectiveCouncilStatus,
  fetchCollectiveCouncilResult,
  preflightCollectiveCouncil,
  runCollectiveCouncil,
  type CouncilPlanResponse,
  type CouncilResultResponse,
  type CollectiveCouncilStatusResponse,
} from "../../api/engagement";
import { sanitizeHostedHtml } from "../../lib/sanitizeHostedHtml";
import { openWindow } from "../windows/openWindow";

type MemberConfig = {
  spawnId: string;
  role: string;
  modelId: string;
  projectedMaxCents: number;
};

export type LiveCouncilPanelProps = {
  selectedSpawnIds: string[];
  collectiveId?: string | null;
  parentAssetId?: string | null;
};

function verifiedCouncilStatus(status: CollectiveCouncilStatusResponse): CollectiveCouncilStatusResponse {
  if (
    status?.view_format !== "html" ||
    status?.product_panel !== "collective_council_status" ||
    typeof status.substrate_available !== "boolean" ||
    typeof status.executor_installed !== "boolean" ||
    typeof status.ledger_installed !== "boolean" ||
    typeof status.live_ready !== "boolean" ||
    typeof status.offline_convergence_available !== "boolean" ||
    typeof status.operator_gated !== "boolean" ||
    !Array.isArray(status.notes) ||
    status.notes.some((note) => typeof note !== "string") ||
    status.live_ready !== (status.executor_installed && status.ledger_installed)
  ) {
    throw new Error("invalid council readiness response");
  }
  return status;
}

export function LiveCouncilPanel({
  selectedSpawnIds,
  collectiveId = null,
  parentAssetId = null,
}: LiveCouncilPanelProps) {
  const selectionKey = selectedSpawnIds.join("\u001f");
  const selectionKeyRef = useRef(selectionKey);
  selectionKeyRef.current = selectionKey;
  const [members, setMembers] = useState<MemberConfig[]>([]);
  const [prompt, setPrompt] = useState("");
  const [synthModel, setSynthModel] = useState("");
  const [synthMaxCents, setSynthMaxCents] = useState(100);
  const [plan, setPlan] = useState<CouncilPlanResponse | null>(null);
  const [result, setResult] = useState<CouncilResultResponse | null>(null);
  const [reviewed, setReviewed] = useState(false);
  const [promotionIds, setPromotionIds] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [convergence, setConvergence] = useState<Record<string, unknown> | null>(null);
  const [readiness, setReadiness] = useState<CollectiveCouncilStatusResponse | null>(null);
  const [readinessError, setReadinessError] = useState(false);

  useEffect(() => {
    let current = true;
    setReadiness(null);
    setReadinessError(false);
    void fetchCollectiveCouncilStatus()
      .then((status) => {
        if (current) setReadiness(verifiedCouncilStatus(status));
      })
      .catch(() => {
        if (current) setReadinessError(true);
      });
    return () => {
      current = false;
    };
  }, []);

  useEffect(() => {
    setMembers(
      selectedSpawnIds.map((spawnId, index) => ({
        spawnId,
        role: `evidence-critic-${index + 1}`,
        modelId: "",
        projectedMaxCents: 100,
      })),
    );
    setPlan(null);
    setResult(null);
    setReviewed(false);
    setConvergence(null);
    setError(null);
    setBusy(false);
    // selectionKey intentionally represents the exact ordered council membership.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectionKey]);

  const ceiling = useMemo(
    () => members.reduce((sum, member) => sum + member.projectedMaxCents, 0) + synthMaxCents,
    [members, synthMaxCents],
  );
  const configured =
    members.length > 0 &&
    prompt.trim().length > 0 &&
    synthModel.trim().length > 0 &&
    members.every(
      (member) =>
        member.modelId.trim().length > 0 &&
        member.role.trim().length > 0 &&
        member.projectedMaxCents > 0,
    );

  const updateMember = (index: number, patch: Partial<MemberConfig>) => {
    setMembers((current) =>
      current.map((member, memberIndex) =>
        memberIndex === index ? { ...member, ...patch } : member,
      ),
    );
  };

  const preflight = async () => {
    if (!configured) return;
    const requestedSelection = selectionKey;
    setBusy(true);
    setError(null);
    try {
      const next = await preflightCollectiveCouncil({
        collective_id: String(collectiveId || `selection-${selectionKey}`).trim(),
        shared_prompt: prompt.trim(),
        members: members.map((member) => ({
          spawn_id: member.spawnId,
          role: member.role.trim(),
          model_id: member.modelId.trim(),
          projected_max_cents: member.projectedMaxCents,
        })),
        synthesizer_model_id: synthModel.trim(),
        synthesizer_projected_max_cents: synthMaxCents,
        approved_ceiling_cents: ceiling,
      });
      if (selectionKeyRef.current !== requestedSelection) return;
      setPlan(next);
      setReviewed(false);
      setResult(null);
    } catch (cause) {
      if (selectionKeyRef.current === requestedSelection) {
        setError(cause instanceof Error ? cause.message : "Council preflight failed");
      }
    } finally {
      if (selectionKeyRef.current === requestedSelection) setBusy(false);
    }
  };

  const approve = async () => {
    if (!plan || !reviewed) return;
    const requestedSelection = selectionKey;
    setBusy(true);
    setError(null);
    try {
      const next = await approveCollectiveCouncil(plan);
      if (selectionKeyRef.current !== requestedSelection) return;
      setPlan(next);
    } catch (cause) {
      if (selectionKeyRef.current === requestedSelection) {
        setError(cause instanceof Error ? cause.message : "Council approval failed");
      }
    } finally {
      if (selectionKeyRef.current === requestedSelection) setBusy(false);
    }
  };

  const run = async () => {
    if (!plan || plan.state !== "approved") return;
    const requestedSelection = selectionKey;
    setBusy(true);
    setError(null);
    try {
      const execution = await runCollectiveCouncil(plan.plan_id, Math.min(4, members.length));
      const next = await fetchCollectiveCouncilResult(execution.result_id);
      if (selectionKeyRef.current !== requestedSelection) return;
      setResult(next);
    } catch (cause) {
      if (selectionKeyRef.current === requestedSelection) {
        setError(cause instanceof Error ? cause.message : "Council execution failed");
      }
    } finally {
      if (selectionKeyRef.current === requestedSelection) setBusy(false);
    }
  };

  const converge = async (
    mode: "offline_collective" | "draft_combined" | "into_parent",
  ) => {
    if (!plan || !result?.result_sha256) return;
    const requestedSelection = selectionKey;
    setBusy(true);
    setError(null);
    try {
      const next = await convergeCollectiveCouncil({
          plan_id: plan.plan_id,
          result_id: result.result_id,
          expected_result_sha256: result.result_sha256,
          mode,
          parent_asset_id: parentAssetId,
          promotion_note_ids: promotionIds
            .split(",")
            .map((value) => value.trim())
            .filter(Boolean),
        });
      if (selectionKeyRef.current !== requestedSelection) return;
      setConvergence(next);
    } catch (cause) {
      if (selectionKeyRef.current === requestedSelection) {
        setError(cause instanceof Error ? cause.message : "Council convergence failed");
      }
    } finally {
      if (selectionKeyRef.current === requestedSelection) setBusy(false);
    }
  };

  return (
    <section
      className="mt-4 border-l-4 border-black bg-white p-4 shadow-[4px_4px_0_0_#111]"
      data-testid="live-council-panel"
      data-council-state={result?.state || plan?.state || "configure"}
      data-selected-count={members.length}
      data-view-format="html"
      data-live-ready={readiness?.live_ready ? "true" : "false"}
      aria-label="Live collective council"
    >
      <header className="mb-3 flex flex-wrap items-start justify-between gap-3 border-b border-black pb-3">
        <div>
          <p className="font-mono text-[10px] uppercase tracking-[0.18em]">L6 · paid boundary</p>
          <h3 className="text-base font-semibold">Council ledger</h3>
          <p className="text-xs opacity-75">
            Review evidence, models, and the exact ceiling before any call can run.
          </p>
        </div>
        <output
          className="border border-black bg-[#dff4ff] px-3 py-2 font-mono text-sm"
          data-testid="council-exact-ceiling"
        >
          ceiling {ceiling}¢
        </output>
      </header>

      <div className="grid gap-3">
        <div
          className={`border border-black p-2 text-xs ${readiness?.live_ready ? "bg-green-50" : "bg-[#fff4bd]"}`}
          role="status"
          data-testid="council-live-readiness"
        >
          {readiness?.live_ready
            ? "Live paid execution ready · exact approval and ceiling still required."
            : readinessError
              ? "Live readiness could not be verified · paid execution remains locked."
              : readiness
                ? "Execution substrate installed; paid runtime is operator-gated and currently unavailable."
                : "Checking paid execution readiness…"}
          {readiness && !readiness.live_ready ? (
            <> · <a className="underline" href="/settings#collective-live-council-status">Open council settings</a></>
          ) : null}
        </div>
        <label className="grid gap-1 text-xs">
          Shared council question
          <textarea
            value={prompt}
            onChange={(event) => setPrompt(event.target.value)}
            disabled={Boolean(plan) || busy}
            rows={3}
            data-testid="council-shared-prompt"
          />
        </label>

        <div className="grid gap-2" data-testid="council-member-ledger">
          {members.map((member, index) => (
            <fieldset key={member.spawnId} className="grid gap-2 border border-black p-2 sm:grid-cols-3">
              <legend className="px-1 font-mono text-[10px]">{member.spawnId}</legend>
              <label className="grid gap-1 text-[11px]">
                Role
                <input
                  value={member.role}
                  onChange={(event) => updateMember(index, { role: event.target.value })}
                  disabled={Boolean(plan) || busy}
                />
              </label>
              <label className="grid gap-1 text-[11px]">
                Model ID
                <input
                  value={member.modelId}
                  onChange={(event) => updateMember(index, { modelId: event.target.value })}
                  disabled={Boolean(plan) || busy}
                  data-testid={`council-member-model-${index}`}
                />
              </label>
              <label className="grid gap-1 text-[11px]">
                Maximum cents
                <input
                  type="number"
                  min={1}
                  value={member.projectedMaxCents}
                  onChange={(event) =>
                    updateMember(index, { projectedMaxCents: Number(event.target.value) })
                  }
                  disabled={Boolean(plan) || busy}
                />
              </label>
            </fieldset>
          ))}
        </div>

        <div className="grid gap-2 sm:grid-cols-2">
          <label className="grid gap-1 text-xs">
            Synthesizer model ID
            <input
              value={synthModel}
              onChange={(event) => setSynthModel(event.target.value)}
              disabled={Boolean(plan) || busy}
              data-testid="council-synth-model"
            />
          </label>
          <label className="grid gap-1 text-xs">
            Synthesizer maximum cents
            <input
              type="number"
              min={1}
              value={synthMaxCents}
              onChange={(event) => setSynthMaxCents(Number(event.target.value))}
              disabled={Boolean(plan) || busy}
            />
          </label>
        </div>

        {!plan ? (
          <button type="button" onClick={() => void preflight()} disabled={!configured || busy}>
            I · Freeze council for review
          </button>
        ) : null}

        {plan?.state === "preflight" ? (
          <div className="grid gap-2 border border-black bg-[#fff4bd] p-3" data-testid="council-review">
            <p className="font-mono text-[11px]">input {plan.input_sha256}</p>
            <ul className="text-xs">
              {plan.members.map((member) => (
                <li key={member.spawn_id}>
                  {member.role} · {member.model_id} · {member.projected_max_cents}¢ · evidence {member.evidence_sha256.slice(0, 12)}
                </li>
              ))}
            </ul>
            <label className="flex items-start gap-2 text-xs">
              <input
                type="checkbox"
                checked={reviewed}
                onChange={(event) => setReviewed(event.target.checked)}
              />
              I reviewed the immutable evidence, models, roles, and {plan.approved_ceiling_cents}¢ ceiling.
            </label>
            <button type="button" onClick={() => void approve()} disabled={!reviewed || busy}>
              II · Approve exact ceiling
            </button>
          </div>
        ) : null}

        {plan?.state === "approved" ? (
          <div className="flex flex-wrap gap-2">
            <button type="button" onClick={() => void run()} disabled={busy || !readiness?.live_ready} data-testid="council-run">
              III · Run approved council · maximum {plan.approved_ceiling_cents}¢
            </button>
            <button type="button" data-testid="council-open-workspace" onClick={() => openWindow("collective_council", { resume_ref: { plan_id: plan.plan_id } }, { id: `win:collective_council:${plan.plan_id}`, title: "Research council", mode: "floating" })}>
              Open resumable council
            </button>
          </div>
        ) : null}

        {result ? (
          <div className="grid gap-3 border-t border-black pt-3" data-testid="council-result">
            <p className="font-mono text-xs">
              {result.state} · spent {result.spent_cents}¢ · held {result.held_cents}¢
            </p>
            <ul className="grid gap-1 text-xs">
              {result.member_receipts.map((receipt) => (
                <li key={receipt.role} className="border border-black px-2 py-1">
                  {receipt.role} · {receipt.state} · {receipt.actual_cents ?? "unknown"}¢ · {receipt.model_id}
                </li>
              ))}
            </ul>
            {result.html ? (
              <div
                className="max-h-80 overflow-auto border border-black p-3"
                data-testid="council-html-result"
                dangerouslySetInnerHTML={{ __html: sanitizeHostedHtml(result.html) }}
              />
            ) : null}
            {result.state === "complete" ? (
              <div className="grid gap-2 border-t border-black pt-3">
                <label className="grid gap-1 text-xs">
                  Existing twin note IDs to promote (optional, comma-separated)
                  <input value={promotionIds} onChange={(event) => setPromotionIds(event.target.value)} />
                </label>
                <div className="flex flex-wrap gap-2">
                  <button type="button" onClick={() => void converge("offline_collective")} disabled={busy}>
                    Keep as offline cohesive unit
                  </button>
                  <button
                    type="button"
                    onClick={() => void converge("draft_combined")}
                    disabled={busy || !parentAssetId}
                  >
                    Create review draft
                  </button>
                  <button
                    type="button"
                    onClick={() => void converge("into_parent")}
                    disabled={busy || !parentAssetId}
                  >
                    Merge into parent
                  </button>
                </div>
              </div>
            ) : null}
          </div>
        ) : null}

        {convergence ? (
          <p className="font-mono text-xs" role="status" data-testid="council-convergence-complete">
            Convergence decision recorded · {String(convergence.action_id || "receipt available")}
          </p>
        ) : null}
        {error ? (
          <p className="border border-red-700 bg-red-50 p-2 text-xs text-red-900" role="alert">
            {error}
          </p>
        ) : null}
      </div>
    </section>
  );
}

export default LiveCouncilPanel;
