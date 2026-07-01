import { useCallback, useEffect, useRef, useState } from "react";

import {
  getDeliverable,
  type DeliverableDetailResponse,
  type DeliverableKind,
} from "../../lib/api";

export const CREATION_DELIVERABLE_REFRESH_EVENT =
  "antiek:creation:deliverable-refresh";

const DELIVERABLE_KIND_LABELS: Record<DeliverableKind, string> = {
  research_memo: "Research memo",
  book_chapter: "Book chapter",
  biography_section: "Biography section",
  investor_brief: "Investor brief",
  general_essay: "General essay",
};

type Props = {
  deliverableId?: string;
};

export default function DeliverablePreview({ deliverableId }: Props) {
  const [detail, setDetail] = useState<DeliverableDetailResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const reloadGenerationRef = useRef(0);
  const detailRef = useRef<DeliverableDetailResponse | null>(null);

  const reload = useCallback(async (options?: { clearCurrent?: boolean }) => {
    const previousDetail = detailRef.current;
    if (!deliverableId) {
      reloadGenerationRef.current += 1;
      detailRef.current = null;
      setDetail(null);
      setLoading(false);
      setError(null);
      return;
    }
    const generation = reloadGenerationRef.current + 1;
    reloadGenerationRef.current = generation;
    setLoading(true);
    setError(null);
    setDetail((prev) =>
      !options?.clearCurrent && prev?.deliverable_id === deliverableId
        ? prev
        : null,
    );
    try {
      const nextDetail = await getDeliverable(deliverableId);
      if (generation === reloadGenerationRef.current) {
        detailRef.current = nextDetail;
        setDetail(nextDetail);
      }
    } catch (e: unknown) {
      if (generation === reloadGenerationRef.current) {
        const fallback =
          previousDetail?.deliverable_id === deliverableId
            ? previousDetail
            : null;
        detailRef.current = fallback;
        setDetail(fallback);
        setError(e instanceof Error ? e.message : String(e));
      }
    } finally {
      if (generation === reloadGenerationRef.current) {
        setLoading(false);
      }
    }
  }, [deliverableId]);

  useEffect(() => {
    detailRef.current = detail;
  }, [detail]);

  useEffect(() => {
    void reload();
    return () => {
      reloadGenerationRef.current += 1;
    };
  }, [reload]);

  useEffect(() => {
    if (!deliverableId) return;
    const onDeliverableRefresh = (event: Event) => {
      const payload = (event as CustomEvent<{ deliverableId?: string }>).detail;
      if (payload?.deliverableId === deliverableId) {
        void reload({ clearCurrent: true });
      }
    };
    window.addEventListener(
      CREATION_DELIVERABLE_REFRESH_EVENT,
      onDeliverableRefresh,
    );
    return () => {
      window.removeEventListener(
        CREATION_DELIVERABLE_REFRESH_EVENT,
        onDeliverableRefresh,
      );
    };
  }, [deliverableId, reload]);
  const activeDetail =
    detail?.deliverable_id === deliverableId ? detail : null;

  if (!deliverableId) {
    return (
      <div className="h-full p-3 bg-ice-0 dark:bg-charcoal-2 text-[12px] font-mono italic text-ink-mute dark:text-moonlight">
        No deliverable selected.
      </div>
    );
  }

  return (
    <article className="h-full overflow-y-auto bg-ice-0 dark:bg-charcoal-2 p-4">
      <header className="mb-4 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[10px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
            Preview
          </p>
          <h2 className="truncate text-lg font-serif text-ink dark:text-bright">
            {activeDetail?.title ?? "Loading deliverable..."}
          </h2>
          {activeDetail && (
            <p className="text-[11px] font-mono text-ink-mute dark:text-moonlight">
              {DELIVERABLE_KIND_LABELS[activeDetail.deliverable_kind] ??
                activeDetail.deliverable_kind}
            </p>
          )}
        </div>
        <button
          type="button"
          onClick={() => void reload({ clearCurrent: true })}
          disabled={loading}
          className="shrink-0 text-[10px] font-mono text-sun-deep dark:text-sun hover:underline disabled:text-ink-mute"
        >
          {loading ? "refreshing" : "refresh"}
        </button>
      </header>

      {error && (
        <p className="mb-3 text-[12px] font-mono text-emperor">{error}</p>
      )}

      {!activeDetail ? (
        <p className="text-[12px] italic text-ink-mute dark:text-moonlight">
          {loading ? "Preparing preview..." : "Preview unavailable."}
        </p>
      ) : activeDetail.sections.length === 0 ? (
        <p className="text-[12px] italic text-ink-mute dark:text-moonlight">
          Add a section to see the export preview.
        </p>
      ) : (
        <div className="space-y-5">
          {activeDetail.sections.map((section) => (
            <section key={section.section_id} className="font-serif">
              <h3 className="mb-2 text-[15px] font-semibold text-ink dark:text-bright">
                {section.title || `Section ${section.section_index + 1}`}
              </h3>
              {section.prose_text ? (
                <div className="space-y-2 text-[14px] leading-relaxed text-ink dark:text-bright">
                  {section.prose_text.split(/\n{2,}/).map((paragraph, index) => (
                    <p key={`${section.section_id}:${index}`} className="whitespace-pre-line">
                      {paragraph}
                    </p>
                  ))}
                </div>
              ) : (
                <p className="text-[12px] italic text-ink-mute dark:text-moonlight">
                  No prose drafted yet.
                </p>
              )}
              <p className="mt-2 text-[10px] font-mono text-shadow-1 dark:text-moonlight">
                {section.block_count} source block
                {section.block_count === 1 ? "" : "s"}
              </p>
            </section>
          ))}
        </div>
      )}
    </article>
  );
}
