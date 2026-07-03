import { useCallback, useEffect, useState } from "react";

import { useViewportTier } from "../../workspace/useViewportTier";
import LemonCard from "../../components/lemon/LemonCard";
import { LemonTag } from "../../components/lemon";
import { useProviderKeys } from "../../hooks/useProviderKeys";
import { apiFetch } from "../../lib/api";
import type {
  AdrbDogfoodStatusView,
  ReadActivationStatusView,
} from "../Coordination/Roadmap";

/**
 * Operator Settings.
 *
 * Honest operator readout for the settings that already have substrate
 * signals: workspace environment, dispatch provider activation, and
 * the canonical routes where policy/economics controls live.
 */
export default function Settings() {
  const tier = useViewportTier();
  const providerKeys = useProviderKeys();
  const readActivation = useReadActivationStatus();
  const isDark =
    typeof window !== "undefined" &&
    window.matchMedia("(prefers-color-scheme: dark)").matches;
  const reduceMotion =
    typeof window !== "undefined" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  return (
    <div className="h-full overflow-y-auto bg-ice-2 dark:bg-space-2">
      <div className="max-w-3xl mx-auto px-6 py-8 space-y-6">
        <header>
          <h1 className="text-2xl font-serif text-ink dark:text-bright">
            Operator settings
          </h1>
          <p className="text-sm text-ink-soft dark:text-starlight font-serif italic mt-1">
            Live workspace and activation readout. Mutating controls
            stay on their canonical operator surfaces; this page tells
            you what is active before you launch agentic work.
          </p>
        </header>

        <LemonCard title="Workspace environment" elevation="z1">
          <div className="p-4 space-y-3 font-mono text-[13px]">
            <Row label="Viewport tier" value={tier} />
            <Row label="OS theme" value={isDark ? "dark" : "light"} />
            <Row
              label="Reduce motion"
              value={reduceMotion ? "yes" : "no"}
            />
            <Row
              label="UI version"
              value={
                (import.meta.env.VITE_ANTIEK_UI as string | undefined) ??
                "v2"
              }
            />
          </div>
        </LemonCard>

        <LemonCard title="Agentic activation" elevation="z1">
          <div className="p-4 space-y-3">
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-sm font-serif text-ink dark:text-bright">
                  Model provider registry
                </p>
                <p className="text-xs text-ink-soft dark:text-starlight">
                  Mirrors <code className="font-mono">/health.registered_providers</code>;
                  no secret values are exposed here.
                </p>
              </div>
              <ProviderStatusTag status={providerKeys.status} />
            </div>

            {providerKeys.status === "ready" ? (
              <div className="space-y-2">
                <div className="flex flex-wrap gap-2">
                  {providerKeys.providers.map((provider) => (
                    <LemonTag key={provider} colour="aurora" dot>
                      {provider}
                    </LemonTag>
                  ))}
                </div>
                <p className="text-sm text-shadow-1 dark:text-moonlight">
                  Provider keys make live Dialogue and research spin-out sessions eligible
                  for the Read activation walk; closure still requires the
                  dogfood log in <code className="font-mono">specs/activation/golden-path.md</code>.
                </p>
              </div>
            ) : (
              <p className="text-sm text-shadow-1 dark:text-moonlight">
                {providerKeys.status === "loading"
                  ? "Checking provider registry..."
                  : providerKeys.status === "error"
                    ? "Could not read /health; agentic paths should be treated as unavailable."
                    : "No model providers are registered, so agentic research and generation stay inert until activation SPR-03 provider-key setup."}
              </p>
            )}

            <button
              type="button"
              onClick={providerKeys.refresh}
              className="text-xs font-mono text-ink dark:text-bright border border-rule dark:border-charcoal-1 px-2 py-1 rounded hover:bg-ice-1 dark:hover:bg-charcoal-2"
            >
              Refresh provider status
            </button>
          </div>
        </LemonCard>

        <LemonCard title="Read dogfood evidence" elevation="z1">
          <ReadDogfoodStatus status={readActivation} />
        </LemonCard>

        <LemonCard title="Research Bridge dogfood" elevation="z1">
          <AdrbDogfoodStatus status={readActivation} />
        </LemonCard>

        <LemonCard title="Control surfaces" elevation="z1" colour="glacial">
          <div className="p-4 grid gap-2 sm:grid-cols-2">
            <ControlLink href="/trust" title="Trust Center" body="Published privacy, deletion, and training commitments" />
            <ControlLink href="/privacy" title="Privacy dashboard" body="Privacy budgets and deletion controls" />
            <ControlLink href="/coordination/cost-consent" title="Cost + consent" body="Unified spend, escrow, and consent status" />
            <ControlLink href="/operator" title="Operator dashboard" body="Operations snapshot" />
          </div>
        </LemonCard>
      </div>
    </div>
  );
}

type ReadActivationLoadState =
  | { status: "loading"; activation: null; adrb: null; error: null }
  | {
      status: "ready";
      activation: ReadActivationStatusView | null;
      adrb: AdrbDogfoodStatusView | null;
      error: null;
    }
  | { status: "error"; activation: null; adrb: null; error: string };

function useReadActivationStatus(): ReadActivationLoadState {
  const [state, setState] = useState<ReadActivationLoadState>({
    status: "loading",
    activation: null,
    adrb: null,
    error: null,
  });

  const load = useCallback(async () => {
    setState({ status: "loading", activation: null, adrb: null, error: null });
    try {
      const response = await apiFetch("/coordination/roadmap");
      if (!response.ok) {
        throw new Error(`GET /coordination/roadmap failed: HTTP ${response.status}`);
      }
      const body = record(await response.json());
      setState({
        status: "ready",
        activation: safeReadActivationStatus(body?.read_activation),
        adrb: safeAdrbDogfoodStatus(body?.adrb_dogfood),
        error: null,
      });
    } catch (error: unknown) {
      setState({
        status: "error",
        activation: null,
        adrb: null,
        error: error instanceof Error ? error.message : String(error),
      });
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return state;
}

function ReadDogfoodStatus({ status }: { status: ReadActivationLoadState }) {
  if (status.status === "loading") {
    return (
      <div className="p-4 text-sm text-shadow-1 dark:text-moonlight">
        Loading Read activation evidence...
      </div>
    );
  }

  if (status.status === "error") {
    return (
      <div className="p-4 space-y-2">
        <LemonTag colour="danger">unreachable</LemonTag>
        <p className="text-sm text-shadow-1 dark:text-moonlight">
          {status.error}
        </p>
      </div>
    );
  }

  const activation = status.activation;
  if (!activation) {
    return (
      <div className="p-4 space-y-2">
        <LemonTag colour="muted">unavailable</LemonTag>
        <p className="text-sm text-shadow-1 dark:text-moonlight">
          Coordination did not return Read activation evidence status.
        </p>
      </div>
    );
  }

  const required = activation.required_counts ?? {};
  const remaining = activation.remaining_requirements ?? {};
  const requiredValid = required.valid_sessions ?? activation.total_sessions;
  const remainingText = [
    ["valid", remaining.valid_sessions],
    ["live-provider", remaining.live_provider_sessions],
    ["citation-traced", remaining.citation_trace_sessions],
    ["non-library", remaining.non_library_sessions],
  ]
    .filter(([, value]) => Number(value) > 0)
    .map(([label, value]) => `${value} ${label}`)
    .join(", ");
  const nextSession = activation.next_session;

  return (
    <div className="p-4 space-y-3">
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm font-serif text-ink dark:text-bright">
          Read activation dogfood
        </p>
        <LemonTag colour={activation.closure_ready ? "aurora" : "sun"}>
          {activation.closure_ready ? "ready" : activation.state}
        </LemonTag>
      </div>
      <p className="text-xs font-mono text-ink dark:text-bright">
        {activation.valid_sessions}/{requiredValid} required valid (
        {activation.total_sessions} total) ·{" "}
        {activation.live_provider_sessions} live-provider ·{" "}
        {activation.citation_trace_sessions} citation-traced ·{" "}
        {activation.non_library_sessions} non-library · verdict=
        {activation.final_verdict || "missing"}
      </p>
      <p className="text-sm text-shadow-1 dark:text-moonlight">
        {activation.closure_ready
          ? "Closure evidence is mechanically ready; operator judgment remains the product bar."
          : remainingText
            ? `Remaining: ${remainingText}.`
            : activation.state === "invalid_log"
              ? "Dogfood log is malformed; repair the JSONL before counting it."
              : "No dogfood closure evidence is ready yet."}{" "}
        Source:{" "}
        <code className="font-mono">
          {activation.source_path || "reports/read-dogfood.jsonl"}
        </code>
        .
      </p>
      {activation.invalid_session_count > 0 && (
        <p className="text-xs font-mono text-emperor">
          {activation.invalid_session_count} invalid session
          {activation.invalid_session_count === 1 ? "" : "s"} need repair.
        </p>
      )}
      {nextSession && nextSession.next_action !== "none" && (
        <p className="text-xs font-mono text-ink-soft dark:text-starlight">
          Next: {nextSession.recommended_template || nextSession.next_action}
          {nextSession.append_command ? ` · ${nextSession.append_command}` : ""}
        </p>
      )}
    </div>
  );
}

function AdrbDogfoodStatus({ status }: { status: ReadActivationLoadState }) {
  if (status.status === "loading") {
    return (
      <div className="p-4 text-sm text-shadow-1 dark:text-moonlight">
        Loading Research Bridge dogfood evidence...
      </div>
    );
  }

  if (status.status === "error") {
    return (
      <div className="p-4 space-y-2">
        <LemonTag colour="danger">unreachable</LemonTag>
        <p className="text-sm text-shadow-1 dark:text-moonlight">
          {status.error}
        </p>
      </div>
    );
  }

  const dogfood = status.adrb;
  if (!dogfood) {
    return (
      <div className="p-4 space-y-2">
        <LemonTag colour="muted">unavailable</LemonTag>
        <p className="text-sm text-shadow-1 dark:text-moonlight">
          Coordination did not return Research Bridge dogfood evidence status.
        </p>
      </div>
    );
  }

  const missing = dogfood.missing_requirements ?? [];
  const missingText =
    missing.length > 0
      ? missing.slice(0, 3).join("; ") + (missing.length > 3 ? "..." : "")
      : "";

  return (
    <div className="p-4 space-y-3">
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm font-serif text-ink dark:text-bright">
          Deep Research Bridge dogfood
        </p>
        <LemonTag
          colour={
            dogfood.closure_ready
              ? "aurora"
              : dogfood.state === "error"
                ? "danger"
                : "sun"
          }
        >
          {dogfood.closure_ready ? "ready" : dogfood.state}
        </LemonTag>
      </div>
      <p className="text-xs font-mono text-ink dark:text-bright">
        {dogfood.complete_project_entries}/{dogfood.expected_project_count}{" "}
        projects · {dogfood.reconciled_sessions} reconciled · metrics=
        {dogfood.metrics_current ? "current" : "stale/missing"} · verdict A=
        {dogfood.mode_a_verdict || "missing"} B=
        {dogfood.mode_b_verdict || "missing"}
      </p>
      <p className="text-sm text-shadow-1 dark:text-moonlight">
        {dogfood.closure_ready
          ? "Bridge dogfood evidence is mechanically ready; the operator verdict remains the product bar."
          : dogfood.error
            ? `Readiness check failed: ${dogfood.error}`
            : missingText
              ? `Remaining: ${missingText}.`
              : "No bridge dogfood closure evidence is ready yet."}{" "}
        Source:{" "}
        <code className="font-mono">{dogfood.dogfood_root || "runs/adrb"}</code>.
      </p>
      {dogfood.verdict_path && (
        <p className="text-xs font-mono text-ink-soft dark:text-starlight">
          Verdict: {dogfood.verdict_path}
        </p>
      )}
    </div>
  );
}

function ProviderStatusTag({ status }: { status: ReturnType<typeof useProviderKeys>["status"] }) {
  if (status === "ready") return <LemonTag colour="aurora">ready</LemonTag>;
  if (status === "loading") return <LemonTag colour="muted">checking</LemonTag>;
  if (status === "error") return <LemonTag colour="danger">unreachable</LemonTag>;
  return <LemonTag colour="sun">not configured</LemonTag>;
}

function ControlLink({
  href,
  title,
  body,
}: {
  href: string;
  title: string;
  body: string;
}) {
  return (
    <a
      href={href}
      className="block rounded-md border border-rule dark:border-charcoal-1 px-3 py-2 hover:bg-ice-1 dark:hover:bg-charcoal-2 transition-colors"
    >
      <span className="block text-sm font-serif text-ink dark:text-bright">
        {title}
      </span>
      <span className="block text-[11px] font-mono text-shadow-1 dark:text-moonlight">
        {href}
      </span>
      <span className="block text-xs text-ink-soft dark:text-starlight mt-1">
        {body}
      </span>
    </a>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="text-ink-soft dark:text-starlight uppercase tracking-wider text-[11px]">
        {label}
      </span>
      <span className="text-ink dark:text-bright">{value}</span>
    </div>
  );
}

function record(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function nonEmptyString(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

function nullableString(value: unknown): string | null {
  return value == null ? null : nonEmptyString(value);
}

function nonNegativeInteger(value: unknown): number {
  const parsed =
    typeof value === "number"
      ? value
      : typeof value === "string" && value.trim() !== ""
        ? Number(value)
        : Number.NaN;
  return Number.isFinite(parsed) && parsed >= 0 ? Math.floor(parsed) : 0;
}

function stringList(value: unknown): string[] {
  return Array.isArray(value)
    ? value.flatMap((item) => {
        const text = nonEmptyString(item);
        return text ? [text] : [];
      })
    : [];
}

function numberRecord(value: unknown): Record<string, number> {
  const body = record(value);
  if (!body) return {};
  return Object.fromEntries(
    Object.entries(body).map(([key, raw]) => [key, nonNegativeInteger(raw)]),
  );
}

function safeReadActivationStatus(value: unknown): ReadActivationStatusView | null {
  const activation = record(value);
  if (!activation) return null;
  const nextSession = record(activation.next_session);
  return {
    source_path: nonEmptyString(activation.source_path) ?? "",
    state: nonEmptyString(activation.state) ?? "not_started",
    total_sessions: nonNegativeInteger(activation.total_sessions),
    valid_sessions: nonNegativeInteger(activation.valid_sessions),
    invalid_session_count: nonNegativeInteger(activation.invalid_session_count),
    live_provider_sessions: nonNegativeInteger(activation.live_provider_sessions),
    citation_trace_sessions: nonNegativeInteger(activation.citation_trace_sessions),
    non_library_sessions: nonNegativeInteger(activation.non_library_sessions),
    final_verdict: nullableString(activation.final_verdict),
    closure_ready: activation.closure_ready === true,
    required_counts: numberRecord(activation.required_counts),
    remaining_requirements: numberRecord(activation.remaining_requirements),
    failures: stringList(activation.failures),
    next_session: nextSession
      ? {
          next_action: nonEmptyString(nextSession.next_action) ?? "collect_session",
          recommended_template: nullableString(nextSession.recommended_template),
          append_command: nullableString(nextSession.append_command),
          rationale: nonEmptyString(nextSession.rationale) ?? "",
          remaining_requirements: numberRecord(nextSession.remaining_requirements),
        }
      : null,
  };
}

function safeAdrbDogfoodStatus(value: unknown): AdrbDogfoodStatusView | null {
  const dogfood = record(value);
  if (!dogfood) return null;
  return {
    state: nonEmptyString(dogfood.state) ?? "not_checked",
    closure_ready: dogfood.closure_ready === true,
    dogfood_root: nonEmptyString(dogfood.dogfood_root) ?? "",
    operator_log_path: nonEmptyString(dogfood.operator_log_path) ?? "",
    metrics_path: nonEmptyString(dogfood.metrics_path) ?? "",
    verdict_path: nonEmptyString(dogfood.verdict_path) ?? "",
    expected_project_count: nonNegativeInteger(dogfood.expected_project_count),
    complete_project_entries: nonNegativeInteger(dogfood.complete_project_entries),
    reconciled_sessions: nonNegativeInteger(dogfood.reconciled_sessions),
    valid_wave4_candidates: nonNegativeInteger(dogfood.valid_wave4_candidates),
    metrics_current: dogfood.metrics_current === true,
    mode_a_verdict: nullableString(dogfood.mode_a_verdict),
    mode_b_verdict: nullableString(dogfood.mode_b_verdict),
    missing_requirements: stringList(dogfood.missing_requirements),
    error: nullableString(dogfood.error),
  };
}
