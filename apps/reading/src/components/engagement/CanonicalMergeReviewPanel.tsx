import { useCallback, useEffect, useRef, useState } from "react";

import {
  commitReviewedMergeDraft,
  type CanonicalMergeCommitResponse,
  type MergeProductResponse,
} from "../../api/engagement";
import { sanitizeHostedHtml } from "../../lib/sanitizeHostedHtml";
import { buildMergedDocWriteHref } from "../../workspace/twinWriteSeed";
import { openWindow } from "../windows/openWindow";

export function canonicalMergeTargetId(...parts: Array<string | null | undefined>): string {
  const safe = (value: string) =>
    value.trim().replace(/[^a-zA-Z0-9_-]+/g, "-").replace(/^-+|-+$/g, "");
  return `dlv-merge-${parts.map((part) => safe(String(part || ""))).filter(Boolean).join("-") || "research"}`;
}

export type CanonicalMergeReviewPanelProps = {
  draft: MergeProductResponse;
  defaultTargetId: string;
  titleStem?: string;
  writeSource?:
    | "spawn_merge"
    | "collective_doc_merge"
    | "collective_written_analysis";
  idPrefix?: string;
  testIdPrefix?: string;
  onCommitted?: (result: CanonicalMergeCommitResponse) => void;
};

export function CanonicalMergeReviewPanel({
  draft,
  defaultTargetId,
  titleStem = "Canonical research",
  writeSource = "spawn_merge",
  idPrefix = "win:canonical-merge",
  testIdPrefix = "canonical-merge",
  onCommitted,
}: CanonicalMergeReviewPanelProps) {
  const [canonicalCommit, setCanonicalCommit] =
    useState<CanonicalMergeCommitResponse | null>(null);
  const [canonicalTarget, setCanonicalTarget] = useState(defaultTargetId);
  const [expectedRevision, setExpectedRevision] = useState("new");
  const [createCombined, setCreateCombined] = useState(true);
  const [commitBusy, setCommitBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const reviewEpoch = useRef(0);
  const commitInFlight = useRef(false);

  useEffect(() => {
    reviewEpoch.current += 1;
    setCanonicalCommit(null);
    setCanonicalTarget(defaultTargetId);
    setExpectedRevision("new");
    setCreateCombined(true);
    setError(null);
    return () => {
      reviewEpoch.current += 1;
    };
  }, [defaultTargetId, draft.document_id, draft.draft_sha256]);

  const invalidateSuccess = () => setCanonicalCommit(null);

  const commitCanonical = useCallback(async () => {
    setCanonicalCommit(null);
    if (
      draft.mode !== "draft_combined" ||
      !draft.draft_sha256?.trim() ||
      !canonicalTarget.trim()
    ) {
      setError("Reviewed draft hash and canonical target are required");
      return;
    }
    const normalizedRevision = expectedRevision.trim();
    if (
      (createCombined && normalizedRevision !== "new") ||
      (!createCombined && (!normalizedRevision || normalizedRevision === "new"))
    ) {
      setError(
        createCombined
          ? 'New combined deliverables require expected revision "new"'
          : "Existing deliverable updates require its current revision hash",
      );
      return;
    }
    if (commitInFlight.current) return;
    commitInFlight.current = true;
    const submitted = {
      epoch: reviewEpoch.current,
      draftDocumentId: draft.document_id,
      draftSha256: draft.draft_sha256,
      targetDeliverableId: canonicalTarget.trim(),
      expectedRevision: normalizedRevision,
      createCombined,
    };
    setCommitBusy(true);
    setError(null);
    try {
      const committed = await commitReviewedMergeDraft({
        draft_document_id: submitted.draftDocumentId,
        reviewed_draft_sha256: submitted.draftSha256,
        target_deliverable_id: submitted.targetDeliverableId,
        expected_revision: submitted.expectedRevision,
        create_combined: submitted.createCombined,
      });
      if (reviewEpoch.current !== submitted.epoch) return;
      if (
        committed.draft_document_id !== submitted.draftDocumentId ||
        committed.draft_sha256 !== submitted.draftSha256 ||
        committed.deliverable_id !== submitted.targetDeliverableId
      ) {
        throw new Error("canonical commit response conflicts with reviewed request");
      }
      if (
        (submitted.createCombined && committed.old_revision !== null) ||
        (!submitted.createCombined &&
          committed.old_revision !== submitted.expectedRevision)
      ) {
        throw new Error("canonical commit response conflicts with revision intent");
      }
      if (committed.view_format !== "html" || !committed.html?.trim()) {
        throw new Error("canonical commit must return HTML");
      }
      setCanonicalCommit(committed);
      onCommitted?.(committed);
    } catch (caught) {
      if (reviewEpoch.current !== submitted.epoch) return;
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      commitInFlight.current = false;
      setCommitBusy(false);
    }
  }, [canonicalTarget, createCombined, draft, expectedRevision, onCommitted]);

  if (draft.mode !== "draft_combined") return null;
  const revisionValid = createCombined
    ? expectedRevision.trim() === "new"
    : Boolean(expectedRevision.trim() && expectedRevision.trim() !== "new");

  return (
    <section
      className="space-y-2 rounded border border-ink/20 p-2 dark:border-bright/20"
      data-testid={`${testIdPrefix}-review`}
      data-draft-document-id={draft.document_id}
      data-reviewed-draft-sha256={draft.draft_sha256 || ""}
      aria-label="Review and commit canonical research"
    >
      <h3 className="text-[12px] font-medium">Commit reviewed draft</h3>
      <p className="text-[10px] font-mono opacity-80">
        Draft <code>{draft.document_id}</code> · review hash{" "}
        <code className="break-all">{draft.draft_sha256 || "missing"}</code>
      </p>
      <label className="block text-[11px] font-mono">
        Canonical deliverable ID
        <input
          data-testid={`${testIdPrefix}-target`}
          value={canonicalTarget}
          onChange={(event) => {
            setCanonicalTarget(event.target.value);
            invalidateSuccess();
          }}
          disabled={commitBusy}
          className="mt-1 block w-full rounded border border-ink/30 bg-transparent px-2 py-1"
        />
      </label>
      <label className="flex items-center gap-2 text-[11px] font-mono">
        <input
          type="checkbox"
          data-testid={`${testIdPrefix}-create-combined`}
          checked={createCombined}
          onChange={(event) => {
            setCreateCombined(event.target.checked);
            invalidateSuccess();
          }}
          disabled={commitBusy}
        />
        Create a new combined deliverable
      </label>
      <label className="block text-[11px] font-mono">
        Expected revision
        <input
          data-testid={`${testIdPrefix}-expected-revision`}
          value={expectedRevision}
          onChange={(event) => {
            setExpectedRevision(event.target.value);
            invalidateSuccess();
          }}
          disabled={commitBusy}
          className="mt-1 block w-full rounded border border-ink/30 bg-transparent px-2 py-1"
        />
      </label>
      <button
        type="button"
        data-testid={`${testIdPrefix}-commit`}
        disabled={
          commitBusy ||
          !draft.draft_sha256?.trim() ||
          !canonicalTarget.trim() ||
          !revisionValid
        }
        onClick={() => void commitCanonical()}
        className="rounded border border-ink/30 px-2 py-1 text-[11px] font-mono disabled:opacity-50"
      >
        {commitBusy ? "Committing…" : "Commit exact reviewed draft"}
      </button>
      {error ? <p className="text-[11px] font-mono text-emperor" role="alert">{error}</p> : null}
      {canonicalCommit ? (
        <div
          data-testid={`${testIdPrefix}-success`}
          data-deliverable-id={canonicalCommit.deliverable_id}
          data-revision={canonicalCommit.new_revision}
          role="status"
        >
          <p className="text-[11px] font-mono text-aurora">
            Canonical <code>{canonicalCommit.deliverable_id}</code> · revision{" "}
            <code>{canonicalCommit.new_revision.slice(0, 12)}</code>
          </p>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              data-testid={`${testIdPrefix}-open-html`}
              onClick={() =>
                openWindow(
                  "hosted_html_document",
                  {
                    document_id: canonicalCommit.deliverable_id,
                    title: `${titleStem} (canonical_commit)`,
                    html: sanitizeHostedHtml(canonicalCommit.html),
                    view_format: "html",
                    source: writeSource,
                  },
                  {
                    id: `${idPrefix}:${canonicalCommit.deliverable_id}`,
                    title: titleStem,
                    mode: "floating",
                  },
                )
              }
              className="rounded border border-ink/30 px-2 py-1 text-[11px] font-mono"
            >
              Open canonical HTML
            </button>
            <a
              data-testid={`${testIdPrefix}-open-write`}
              href={buildMergedDocWriteHref({
                documentId: canonicalCommit.deliverable_id,
                title: `${titleStem} · ${canonicalCommit.deliverable_id}`,
                html: canonicalCommit.html,
                source: writeSource,
              })}
              className="rounded border border-ink/30 px-2 py-1 text-[11px] font-mono underline"
            >
              Open canonical in Write
            </a>
          </div>
        </div>
      ) : null}
    </section>
  );
}

export default CanonicalMergeReviewPanel;
