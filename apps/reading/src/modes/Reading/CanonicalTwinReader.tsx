import { useEffect, useRef, useState } from "react";
import { ChevronDown, CircleHelp, Lightbulb, RotateCw } from "lucide-react";
import { useParams, useSearchParams } from "react-router-dom";

import {
  getCanonicalTwin,
  getCurrentPromotion,
  getReviewedPromotions,
  trustedCanonicalHtml,
} from "../../api/canonicalTwin";
import type {
  CanonicalTwinView,
  CurrentPromotionDetail,
  ReviewedPromotionCollection,
  ReviewedPromotionSummary,
} from "../../api/canonicalTwin";
import { LemonButton, LemonTag } from "../../components/lemon";
import "./canonical-twin-reader.css";

type LoadState =
  | { kind: "loading" }
  | { kind: "invalid" }
  | { kind: "unavailable" }
  | { kind: "ready"; requestKey: string; twin: CanonicalTwinView; promotions: ReviewedPromotionCollection };

export default function CanonicalTwinReader() {
  const { sourceAssetId = "" } = useParams<{ sourceAssetId: string }>();
  const [search] = useSearchParams();
  const revision = search.get("revision") ?? "";
  const requestKey = `${sourceAssetId}\u0000${revision}`;
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<LoadState>(
    sourceAssetId && revision ? { kind: "loading" } : { kind: "invalid" },
  );

  useEffect(() => {
    if (!sourceAssetId || !revision) {
      setState({ kind: "invalid" });
      return;
    }
    const controller = new AbortController();
    setState({ kind: "loading" });
    void (async () => {
      try {
        const twin = await getCanonicalTwin(sourceAssetId, revision, controller.signal);
        if (
          twin.source_asset_id !== sourceAssetId ||
          twin.source_hash !== revision ||
          twin.authority !== "advisory" ||
          twin.shareable !== false
        ) {
          throw new Error("canonical_twin_identity_conflict");
        }
        const promotions = await getReviewedPromotions(
          twin.reviewed_promotions_href,
          controller.signal,
        );
        if (
          promotions.source_asset_id !== sourceAssetId ||
          promotions.source_hash !== revision ||
          promotions.complete !== true
        ) {
          throw new Error("reviewed_promotions_identity_conflict");
        }
        trustedCanonicalHtml(twin.html_fragment);
        setState({ kind: "ready", requestKey, twin, promotions });
      } catch (error) {
        if (!controller.signal.aborted) setState({ kind: "unavailable" });
      }
    })();
    return () => controller.abort();
  }, [attempt, revision, sourceAssetId]);

  const visibleState: LoadState =
    state.kind === "ready" && state.requestKey !== requestKey ? { kind: "loading" } : state;
  if (visibleState.kind !== "ready") {
    return (
      <main className="twin-reader-state">
        <div role={visibleState.kind === "loading" ? "status" : "alert"}>
          <p className="twin-reader-kicker">Canonical twin</p>
          <h1>
            {visibleState.kind === "loading"
              ? "Opening this revision"
              : visibleState.kind === "invalid"
                ? "An exact revision is required"
                : "This revision is unavailable"}
          </h1>
          <p>
            {visibleState.kind === "loading"
              ? "Checking the current document and its reviewed notes."
              : visibleState.kind === "invalid"
                ? "Open this view from a canonical twin link that includes its revision."
                : "The document or one of its reviewed notes no longer has current authority."}
          </p>
          {visibleState.kind === "unavailable" && (
            <LemonButton size="sm" variant="secondary" onClick={() => setAttempt((n) => n + 1)}>
              <RotateCw size={14} aria-hidden="true" /> Retry
            </LemonButton>
          )}
        </div>
      </main>
    );
  }

  return (
    <main className="twin-reader-shell">
      <section className="twin-reader-document" aria-labelledby="twin-reader-title">
        <header className="twin-reader-header">
          <div>
            <p className="twin-reader-kicker">Canonical twin</p>
            <h1 id="twin-reader-title">{visibleState.twin.title}</h1>
          </div>
          <LemonTag colour="muted">Private advisory</LemonTag>
        </header>
        <p className="twin-reader-authority">{visibleState.twin.authority_label}</p>
        <article
          className="twin-reader-prose"
          data-document-id={visibleState.twin.document_id}
          dangerouslySetInnerHTML={{ __html: visibleState.twin.html_fragment }}
        />
      </section>

      <aside className="twin-reader-margin" aria-label="Reviewed notes">
        <header>
          <p className="twin-reader-kicker">Owner reviewed</p>
          <h2>Insights and questions</h2>
          <p>Each item remains visible only while its review, source evidence, and citations agree.</p>
        </header>
        {visibleState.promotions.items.length === 0 ? (
          <div className="twin-reader-empty">
            <p>No reviewed notes for this revision.</p>
          </div>
        ) : (
          <ol className="twin-reader-notes">
            {visibleState.promotions.items.map((item) => (
              <li key={`${visibleState.twin.document_id}:${item.candidate_id}`}>
                <ReviewedNote item={item} twinDocumentId={visibleState.twin.document_id} />
              </li>
            ))}
          </ol>
        )}
      </aside>
    </main>
  );
}

function ReviewedNote({
  item,
  twinDocumentId,
}: {
  item: ReviewedPromotionSummary;
  twinDocumentId: string;
}) {
  const [open, setOpen] = useState(false);
  const [detail, setDetail] = useState<CurrentPromotionDetail | null>(null);
  const [pending, setPending] = useState(false);
  const [withheld, setWithheld] = useState(false);
  const requestRef = useRef<AbortController | null>(null);

  useEffect(() => () => requestRef.current?.abort(), [item.candidate_id]);

  async function toggle() {
    if (open) {
      setOpen(false);
      return;
    }
    if (detail) {
      setOpen(true);
      return;
    }
    setPending(true);
    setWithheld(false);
    requestRef.current?.abort();
    const controller = new AbortController();
    requestRef.current = controller;
    try {
      const value = await getCurrentPromotion(item.href, controller.signal);
      const ownerId = value.node.owner_id;
      const citationIds = new Set(value.citations.map((citation) => citation.citation_id));
      const candidateDigests = new Set(value.citations.map((citation) => citation.candidate_digest));
      if (
        value.node.candidate_id !== item.candidate_id ||
        value.node.node_id !== item.node_id ||
        value.node.review_id !== item.review_id ||
        value.node.text !== item.text ||
        value.node.kind !== item.kind ||
        value.node.status !== "current" ||
        value.node.authority !== "owner_reviewed_evidence_bound_graph_node_v1" ||
        value.status !== "current" ||
        value.authority !== "owner_reviewed_evidence_bound_node_citations_v1" ||
        value.citations.length !== item.evidence_count + 1 ||
        citationIds.size !== value.citations.length ||
        candidateDigests.size !== 1 ||
        value.citations.some(
          (citation, index) =>
            citation.ordinal !== index ||
            citation.node_id !== item.node_id ||
            citation.candidate_id !== item.candidate_id ||
            citation.review_id !== item.review_id ||
            citation.owner_id !== ownerId ||
            citation.schema !== "antiek.canonical-twin-node-citation.v1" ||
            !/^[0-9a-f]{64}$/.test(citation.candidate_digest) ||
            !/^[0-9a-f]{64}$/.test(citation.text_sha256) ||
            !/^[0-9a-f]{64}$/.test(citation.chunk_sha256) ||
            (index === 0
              ? citation.citation_kind !== "canonical_twin" ||
                citation.document_id !== twinDocumentId ||
                citation.range_start !== null ||
                citation.range_end !== null
              : citation.citation_kind !== "evidence"),
        )
      ) {
        throw new Error("reviewed_promotion_identity_conflict");
      }
      if (!controller.signal.aborted) {
        setDetail(value);
        setOpen(true);
      }
    } catch {
      if (!controller.signal.aborted) setWithheld(true);
    } finally {
      if (!controller.signal.aborted) setPending(false);
    }
  }

  const Icon = item.kind === "question" ? CircleHelp : Lightbulb;
  return (
    <section className="twin-reviewed-note">
      <div className="twin-reviewed-note-heading">
        <Icon size={16} aria-hidden="true" />
        <p>{item.text}</p>
      </div>
      <button
        type="button"
        className="twin-evidence-toggle"
        aria-expanded={open}
        disabled={pending}
        onClick={() => void toggle()}
      >
        <span>{pending ? "Checking evidence" : `${item.evidence_count} evidence source${item.evidence_count === 1 ? "" : "s"}`}</span>
        <ChevronDown size={15} aria-hidden="true" className={open ? "is-open" : ""} />
      </button>
      {withheld && (
        <p className="twin-evidence-withheld" role="status">
          Evidence is not currently available.
        </p>
      )}
      {open && detail && (
        <ol className="twin-citation-spine">
          {detail.citations.map((citation) => (
            <li key={citation.citation_id}>
              <span>{citation.ordinal + 1}</span>
              <div>
                <strong>{citation.citation_kind === "canonical_twin" ? "Canonical note" : "Source evidence"}</strong>
                <p>
                  {citation.range_start === null
                    ? "Whole supporting chunk"
                    : `Characters ${citation.range_start}–${citation.range_end}`}
                </p>
              </div>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
