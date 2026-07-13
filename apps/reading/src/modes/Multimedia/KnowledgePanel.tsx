import { useEffect, useRef, useState } from "react";

import {
  finalizeMultimediaKnowledge,
  getMultimediaKnowledgeFinalization,
  getMultimediaKnowledgeTwin,
  recoverMultimediaKnowledgeFinalization,
} from "../../api/multimedia";
import type {
  MultimediaAssetRecord,
  MultimediaKnowledgeFinalizationStatus,
  MultimediaTwinDocument,
} from "../../api/multimedia";
import { LemonButton, LemonTag } from "../../components/lemon";

type Props = {
  asset: MultimediaAssetRecord;
  onAssetUpdated: (asset: MultimediaAssetRecord) => void;
  onMutationBusyChange?: (busy: boolean) => void;
};

type Pending = "inspect" | "finalize" | "recover" | "open" | null;

export function retainCurrentMultimediaSelection(
  current: MultimediaAssetRecord | null,
  expectedAssetId: string,
  expectedRevisionId: string,
  updated: MultimediaAssetRecord,
): MultimediaAssetRecord | null {
  if (
    current?.asset.asset_id !== expectedAssetId ||
    current.asset.revision_id !== expectedRevisionId
  ) {
    return current;
  }
  return updated;
}

const STATE_LABELS = {
  not_started: "Not started",
  in_progress: "In progress",
  completed: "Twin ready",
  integrity_conflict: "Integrity review",
} as const;

function errorMessage(error: unknown): string {
  const code = error instanceof Error ? error.message : "";
  if (code === "multimedia_knowledge_runtime_unavailable") return "Knowledge runtime is unavailable.";
  if (code === "multimedia_knowledge_unavailable") return "This asset is no longer available.";
  if (code === "multimedia_knowledge_conflict") return "The asset or recovery state changed. Refresh before trying again.";
  if (code === "multimedia_twin_unavailable") return "The knowledge twin is no longer available.";
  if (code === "multimedia_twin_integrity_conflict") return "The knowledge twin failed its integrity check.";
  return "Could not update the knowledge twin.";
}

function assertFinalizationResponseIdentity(
  expected: MultimediaAssetRecord,
  result: Awaited<ReturnType<typeof finalizeMultimediaKnowledge>>,
): void {
  const assetId = expected.asset.asset_id;
  const revisionId = expected.asset.revision_id;
  if (
    result.asset.asset.asset_id !== assetId ||
    result.asset.asset.revision_id !== revisionId ||
    result.knowledge_link.asset_id !== assetId ||
    result.knowledge_link.revision_id !== revisionId
  ) {
    throw new Error("multimedia_knowledge_conflict");
  }
}

export function KnowledgePanel({ asset, onAssetUpdated, onMutationBusyChange }: Props) {
  const [status, setStatus] = useState<MultimediaKnowledgeFinalizationStatus | null>(null);
  const [pending, setPending] = useState<Pending>(null);
  const [modelAcknowledged, setModelAcknowledged] = useState(false);
  const [duplicateRiskAcknowledged, setDuplicateRiskAcknowledged] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [viewer, setViewer] = useState<MultimediaTwinDocument | null>(null);
  const readEpoch = useRef(0);
  const currentIdentity = useRef("");

  const ready = asset.asset.status === "ready";
  const identity = `${asset.asset.asset_id}:${asset.asset.revision_id}`;
  currentIdentity.current = identity;

  async function inspect() {
    const requestEpoch = ++readEpoch.current;
    const requestIdentity = identity;
    setPending("inspect");
    try {
      const next = await getMultimediaKnowledgeFinalization(asset.asset.asset_id);
      if (
        requestEpoch !== readEpoch.current ||
        requestIdentity !== currentIdentity.current
      ) {
        return;
      }
      const linkIdentityMatches =
        next.knowledge_link === null ||
        (next.knowledge_link.asset_id === asset.asset.asset_id &&
          next.knowledge_link.revision_id === asset.asset.revision_id);
      if (
        next.asset_id !== asset.asset.asset_id ||
        next.revision_id !== asset.asset.revision_id ||
        !linkIdentityMatches
      ) {
        setError("The asset revision changed. Reopen it before continuing.");
        return;
      }
      setStatus(next);
      setError(null);
    } catch (cause) {
      if (
        requestEpoch !== readEpoch.current ||
        requestIdentity !== currentIdentity.current
      ) {
        return;
      }
      setError(errorMessage(cause));
    } finally {
      if (
        requestEpoch === readEpoch.current &&
        requestIdentity === currentIdentity.current
      ) {
        setPending(null);
      }
    }
  }

  useEffect(() => {
    readEpoch.current += 1;
    setStatus(null);
    setModelAcknowledged(false);
    setDuplicateRiskAcknowledged(false);
    setError(null);
    setViewer(null);
    if (ready) void inspect();
    // Asset identity and revision intentionally reset all spend acknowledgements.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [asset.asset.asset_id, asset.asset.revision_id, ready]);

  async function finalize() {
    if (!modelAcknowledged) return;
    setPending("finalize");
    onMutationBusyChange?.(true);
    try {
      const result = await finalizeMultimediaKnowledge(asset.asset.asset_id, asset.asset.revision_id);
      assertFinalizationResponseIdentity(asset, result);
      onAssetUpdated(result.asset);
      setStatus({
        asset_id: result.asset.asset.asset_id,
        revision_id: result.asset.asset.revision_id,
        asset_status: result.asset.asset.status,
        distillation: {
          state: "completed",
          recovery_eligible: false,
          recovery_stale_seconds: 900,
          claim_started_at: null,
        },
        knowledge_link: result.knowledge_link,
      });
      setModelAcknowledged(false);
      setError(null);
    } catch (cause) {
      await inspect();
      setError(errorMessage(cause));
    } finally {
      setPending(null);
      onMutationBusyChange?.(false);
    }
  }

  async function recover() {
    if (!modelAcknowledged || !duplicateRiskAcknowledged) return;
    setPending("recover");
    onMutationBusyChange?.(true);
    try {
      const result = await recoverMultimediaKnowledgeFinalization(
        asset.asset.asset_id,
        asset.asset.revision_id,
      );
      assertFinalizationResponseIdentity(asset, result);
      onAssetUpdated(result.asset);
      setStatus({
        asset_id: result.asset.asset.asset_id,
        revision_id: result.asset.asset.revision_id,
        asset_status: result.asset.asset.status,
        distillation: {
          state: "completed",
          recovery_eligible: false,
          recovery_stale_seconds: 900,
          claim_started_at: null,
        },
        knowledge_link: result.knowledge_link,
      });
      setModelAcknowledged(false);
      setDuplicateRiskAcknowledged(false);
      setError(null);
    } catch (cause) {
      await inspect();
      setError(errorMessage(cause));
    } finally {
      setPending(null);
      onMutationBusyChange?.(false);
    }
  }

  async function openTwin() {
    if (!link || state !== "completed") return;
    const requestEpoch = ++readEpoch.current;
    const requestIdentity = identity;
    setPending("open");
    try {
      const document = await getMultimediaKnowledgeTwin(asset.asset.asset_id);
      if (
        requestEpoch !== readEpoch.current ||
        requestIdentity !== currentIdentity.current
      ) {
        return;
      }
      if (
        document.asset_id !== asset.asset.asset_id ||
        document.revision_id !== asset.asset.revision_id ||
        document.source_document_id !== link.source_document_id ||
        document.twin_document_id !== link.twin_document_id ||
        document.html_sha256 !== link.twin_html_sha256
      ) {
        throw new Error("multimedia_twin_integrity_conflict");
      }
      setViewer(document);
      setError(null);
    } catch (cause) {
      if (
        requestEpoch !== readEpoch.current ||
        requestIdentity !== currentIdentity.current
      ) {
        return;
      }
      setViewer(null);
      setError(errorMessage(cause));
    } finally {
      if (
        requestEpoch === readEpoch.current &&
        requestIdentity === currentIdentity.current
      ) {
        setPending(null);
      }
    }
  }

  const state = status?.distillation.state ?? "not_started";
  const link = status?.knowledge_link ?? asset.knowledge_link;
  const recovery = Boolean(status?.distillation.recovery_eligible);

  return (
    <section
      className="rounded-md border border-rule bg-ice-0 p-3 dark:border-charcoal-1 dark:bg-charcoal-1"
      data-testid="multimedia-knowledge-panel"
      aria-labelledby="multimedia-knowledge-title"
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <p id="multimedia-knowledge-title" className="font-mono text-[12px] text-shadow-2 dark:text-moonlight">
            Knowledge twin
          </p>
          <p className="mt-1 text-[13px] leading-relaxed text-ink dark:text-bright">
            Preserve the transcript, insights, and open questions as an HTML information asset.
          </p>
        </div>
        <LemonTag colour={state === "completed" ? "aurora" : state === "integrity_conflict" ? "danger" : "default"}>
          {pending === "inspect" ? "Checking" : STATE_LABELS[state]}
        </LemonTag>
      </div>

      {!ready && (
        <p className="mt-3 text-[12px] text-shadow-1 dark:text-moonlight">
          Approve and complete this revision before creating its knowledge twin.
        </p>
      )}

      {ready && state === "not_started" && pending !== "inspect" && (
        <div className="mt-3 space-y-3">
          <Acknowledgement
            checked={modelAcknowledged}
            onChange={setModelAcknowledged}
            label="I approve one note-model call to extract insights and questions."
          />
          <LemonButton type="button" size="sm" variant="primary" disabled={!modelAcknowledged || pending !== null} onClick={finalize}>
            {pending === "finalize" ? "Creating twin..." : "Create knowledge twin"}
          </LemonButton>
        </div>
      )}

      {ready && state === "in_progress" && !recovery && (
        <p className="mt-3 text-[12px] text-shadow-1 dark:text-moonlight">
          A note-model run is still reserved. Recovery becomes available after {status?.distillation.recovery_stale_seconds ?? 900} seconds.
        </p>
      )}

      {ready && recovery && state !== "completed" && (
        <div className="mt-3 space-y-2">
          <p className="text-[12px] leading-relaxed text-danger">
            The previous outcome is uncertain. Recovery can repeat billable model work.
          </p>
          <Acknowledgement checked={modelAcknowledged} onChange={setModelAcknowledged} label="I approve another note-model call." />
          <Acknowledgement checked={duplicateRiskAcknowledged} onChange={setDuplicateRiskAcknowledged} label="I understand this may duplicate model spend." />
          <LemonButton type="button" size="sm" variant="primary" disabled={!modelAcknowledged || !duplicateRiskAcknowledged || pending !== null} onClick={recover}>
            {pending === "recover" ? "Recovering..." : "Recover knowledge twin"}
          </LemonButton>
        </div>
      )}

      {state === "integrity_conflict" && !recovery && (
        <p className="mt-3 text-[12px] text-danger">The checkpoint and claim disagree. Automatic recovery is disabled.</p>
      )}

      {link && state === "completed" && (
        <div className="mt-3">
        <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1 text-[12px]" data-testid="multimedia-knowledge-evidence">
          <dt className="text-shadow-2 dark:text-moonlight">Twin</dt>
          <dd className="truncate text-right font-mono text-ink dark:text-bright" title={link.twin_document_id}>{link.twin_document_id}</dd>
          <dt className="text-shadow-2 dark:text-moonlight">Insights</dt>
          <dd className="text-right text-ink dark:text-bright">{link.insight_node_ids.length}</dd>
          <dt className="text-shadow-2 dark:text-moonlight">Questions</dt>
          <dd className="text-right text-ink dark:text-bright">{link.question_node_ids.length}</dd>
        </dl>
        <LemonButton type="button" size="sm" variant="secondary" className="mt-3" disabled={pending !== null} onClick={openTwin}>
          {pending === "open" ? "Opening..." : "Open twin"}
        </LemonButton>
        </div>
      )}

      {viewer && (
        <section className="mt-3 border-t border-rule pt-3 dark:border-charcoal-1" data-testid="multimedia-twin-viewer">
          <div className="flex items-center justify-between gap-3">
            <h3 className="truncate font-serif text-base text-ink dark:text-bright">{viewer.title}</h3>
            <LemonButton type="button" size="sm" variant="tertiary" onClick={() => setViewer(null)}>Close</LemonButton>
          </div>
          <iframe
            title={viewer.title}
            sandbox=""
            srcDoc={viewer.html}
            className="mt-3 h-[420px] w-full border border-rule bg-white dark:border-charcoal-1"
          />
        </section>
      )}

      {ready && pending !== "inspect" && (
        <LemonButton type="button" size="sm" variant="tertiary" className="mt-3" disabled={pending !== null} onClick={inspect}>
          Refresh status
        </LemonButton>
      )}
      {error && <p className="mt-3 text-[12px] text-danger" role="alert">{error}</p>}
    </section>
  );
}

function Acknowledgement({ checked, onChange, label }: { checked: boolean; onChange: (checked: boolean) => void; label: string }) {
  return (
    <label className="flex items-start gap-2 text-[12px] leading-relaxed text-ink dark:text-bright">
      <input type="checkbox" className="mt-0.5 size-4 accent-primary" checked={checked} onChange={(event) => onChange(event.target.checked)} />
      <span>{label}</span>
    </label>
  );
}
