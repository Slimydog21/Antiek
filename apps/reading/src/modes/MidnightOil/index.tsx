/**
 * Midnight Oil mode — goals + duration → recommended ceiling → explicit approve.
 * HTML deliverable only (view_format html). Worker launch is out of band.
 */

import { useState } from "react";
import {
  approveMidnightOilCeiling,
  createMidnightOilJob,
  depositMidnightOilJob,
  type MidnightOilDepositResponse,
  type MidnightOilJobResponse,
} from "../../api/midnightOil";

export default function MidnightOil() {
  const [goalsText, setGoalsText] = useState("");
  const [durationMinutes, setDurationMinutes] = useState(60);
  const [modelId, setModelId] = useState("default");
  const [job, setJob] = useState<MidnightOilJobResponse | null>(null);
  const [deposit, setDeposit] = useState<MidnightOilDepositResponse | null>(
    null,
  );
  const [ceilingInput, setCeilingInput] = useState("");
  const [forceBelow, setForceBelow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onCreate(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const goals = goalsText
        .split("\n")
        .map((g) => g.trim())
        .filter(Boolean);
      const created = await createMidnightOilJob({
        goals,
        duration_minutes: durationMinutes,
        model_id: modelId || null,
      });
      if (created.view_format !== "html") {
        throw new Error("Midnight Oil view_format must be html");
      }
      setJob(created);
      setCeilingInput(String(created.recommended_price_ceiling_usd));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function onApproveRecommended() {
    if (!job) return;
    setBusy(true);
    setError(null);
    try {
      const approved = await approveMidnightOilCeiling({
        job_id: job.job_id,
        use_recommended: true,
      });
      setJob(approved);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function onApproveCustom() {
    if (!job) return;
    setBusy(true);
    setError(null);
    try {
      const amount = Number(ceilingInput);
      const approved = await approveMidnightOilCeiling({
        job_id: job.job_id,
        ceiling_usd: amount,
        force_below: forceBelow,
      });
      setJob(approved);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function onDeposit() {
    if (!job) return;
    setBusy(true);
    setError(null);
    try {
      const result = await depositMidnightOilJob({
        job_id: job.job_id,
        draft_combined: true,
        record_progress: true,
        mark_complete: true,
        include_progress_html: true,
      });
      if (result.view_format !== "html") {
        throw new Error("deposit view_format must be html");
      }
      setDeposit(result);
      setJob({
        ...job,
        status: result.job_status || "complete",
        asset_id: result.asset_id,
        runnable: false,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      className="h-full overflow-y-auto p-6"
      data-view-format="html"
      data-testid="midnight-oil-mode"
    >
      <header className="mb-6 space-y-1">
        <h1 className="text-2xl font-semibold">Midnight Oil</h1>
        <p className="text-sm opacity-80">
          Autonomous deep research without a live workstation session. Set goals
          and duration; review the recommended price ceiling; approve before work
          may run. Deliverable: HTML research asset (never PDF).
        </p>
      </header>

      <form onSubmit={(e) => void onCreate(e)} className="space-y-4 max-w-xl">
        <label className="block space-y-1">
          <span className="text-sm font-medium">Goals (one per line)</span>
          <textarea
            className="w-full min-h-[120px] border rounded p-2"
            value={goalsText}
            onChange={(e) => setGoalsText(e.target.value)}
            required
            disabled={busy}
          />
        </label>
        <label className="block space-y-1">
          <span className="text-sm font-medium">Duration (minutes)</span>
          <input
            type="number"
            min={1}
            className="w-full border rounded p-2"
            value={durationMinutes}
            onChange={(e) => setDurationMinutes(Number(e.target.value))}
            disabled={busy}
          />
        </label>
        <label className="block space-y-1">
          <span className="text-sm font-medium">Model id</span>
          <input
            type="text"
            className="w-full border rounded p-2"
            value={modelId}
            onChange={(e) => setModelId(e.target.value)}
            disabled={busy}
          />
        </label>
        <button type="submit" disabled={busy || !goalsText.trim()}>
          {busy ? "Working…" : "Create job + recommend ceiling"}
        </button>
      </form>

      {error ? (
        <p className="mt-4 text-red-600" role="alert">
          {error}
        </p>
      ) : null}

      {job ? (
        <section className="mt-8 space-y-3 max-w-xl" data-testid="moil-job">
          <h2 className="text-lg font-medium">Job {job.job_id}</h2>
          <p>
            Status: <strong>{job.status}</strong>
            {job.runnable ? " · runnable" : ""}
          </p>
          <p data-testid="recommended-ceiling">
            Recommended ceiling:{" "}
            <strong>${job.recommended_price_ceiling_usd.toFixed(2)}</strong>
          </p>
          {job.approved_ceiling_usd != null ? (
            <p data-testid="approved-ceiling">
              Approved ceiling:{" "}
              <strong>${job.approved_ceiling_usd.toFixed(2)}</strong>
            </p>
          ) : null}

          {job.status === "awaiting_approval" ? (
            <div className="space-y-2 border rounded p-3">
              <button
                type="button"
                onClick={() => void onApproveRecommended()}
                disabled={busy}
              >
                Approve at recommended
              </button>
              <div className="flex flex-wrap items-center gap-2">
                <input
                  type="number"
                  step="0.01"
                  min="0.01"
                  className="border rounded p-2 w-32"
                  value={ceilingInput}
                  onChange={(e) => setCeilingInput(e.target.value)}
                  disabled={busy}
                />
                <label className="text-sm">
                  <input
                    type="checkbox"
                    checked={forceBelow}
                    onChange={(e) => setForceBelow(e.target.checked)}
                    disabled={busy}
                  />{" "}
                  Force below recommended
                </label>
                <button
                  type="button"
                  onClick={() => void onApproveCustom()}
                  disabled={busy}
                >
                  Approve custom ceiling
                </button>
              </div>
            </div>
          ) : null}

          {job.status === "approved" || job.status === "complete" ? (
            <div className="space-y-2 border rounded p-3">
              <p className="text-sm opacity-80">
                Deposit lands HTML research output + twin notes and seeds
                progress telemetry (plan→cite→complete). Worker may also run
                out-of-band.
              </p>
              <button
                type="button"
                data-testid="moil-deposit"
                onClick={() => void onDeposit()}
                disabled={busy}
              >
                {busy ? "Depositing…" : "Deposit results (HTML + twins)"}
              </button>
            </div>
          ) : null}

          {deposit ? (
            <div
              className="space-y-2 border rounded p-3"
              data-testid="moil-deposit-result"
              data-view-format="html"
            >
              <h3 className="font-medium">Deposit result</h3>
              <p className="font-mono text-sm">
                document=<code>{deposit.document_id}</code> · twins=
                {deposit.twin_count} · usage=
                {String(deposit.usage_recorded)} · progress_seeded=
                {String(deposit.progress_seeded)}
              </p>
              {deposit.progress ? (
                <p className="font-mono text-sm" data-testid="moil-progress-summary">
                  progress latest=
                  <strong>{deposit.progress.latest_stage ?? "(none)"}</strong> ·
                  events={deposit.progress.event_count ?? 0} · terminal=
                  {String(deposit.progress.is_terminal ?? false)}
                </p>
              ) : null}
              {deposit.html ? (
                <div
                  className="prose border rounded p-3 text-sm max-h-64 overflow-auto"
                  data-testid="deposit-html"
                  dangerouslySetInnerHTML={{ __html: deposit.html }}
                />
              ) : null}
              {deposit.progress?.html ? (
                <div
                  className="prose border rounded p-3 text-sm max-h-48 overflow-auto"
                  data-testid="deposit-progress-html"
                  dangerouslySetInnerHTML={{ __html: deposit.progress.html }}
                />
              ) : null}
            </div>
          ) : null}

          {job.html ? (
            <div
              className="prose border rounded p-3 text-sm"
              data-testid="job-html"
              dangerouslySetInnerHTML={{ __html: job.html }}
            />
          ) : null}
        </section>
      ) : null}
    </div>
  );
}
