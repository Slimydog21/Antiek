import type {
  DeliverableDetailResponse,
  DeliverableKind,
  DeliverableSummary,
  SectionResponse,
} from "../../lib/api";

const DELIVERABLE_KINDS = new Set<DeliverableKind>([
  "research_memo",
  "book_chapter",
  "biography_section",
  "investor_brief",
  "general_essay",
]);

function nonEmptyString(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

function nullableString(value: unknown): string | null {
  return value == null ? null : nonEmptyString(value);
}

function finiteNonNegativeNumber(value: unknown): number | null {
  const parsed =
    typeof value === "number"
      ? value
      : typeof value === "string" && value.trim() !== ""
        ? Number(value)
        : Number.NaN;
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : null;
}

function safeKind(value: unknown): DeliverableKind {
  return typeof value === "string" && DELIVERABLE_KINDS.has(value as DeliverableKind)
    ? (value as DeliverableKind)
    : "general_essay";
}

function safeStatus(value: unknown): string {
  return nonEmptyString(value) ?? "draft";
}

export function safeDeliverableSummaries(
  deliverables: DeliverableSummary[],
): DeliverableSummary[] {
  return deliverables.flatMap((deliverable) => {
    const deliverableId = nonEmptyString(deliverable.deliverable_id);
    if (!deliverableId) return [];
    return [
      {
        ...deliverable,
        deliverable_id: deliverableId,
        title: nonEmptyString(deliverable.title) ?? "Untitled piece",
        deliverable_kind: safeKind(deliverable.deliverable_kind),
        investigation_root_id: nullableString(deliverable.investigation_root_id),
        status: safeStatus(deliverable.status),
        section_count: finiteNonNegativeNumber(deliverable.section_count) ?? 0,
      },
    ];
  });
}

export function safeSections(sections: SectionResponse[]): SectionResponse[] {
  return sections.flatMap((section) => {
    const sectionId = nonEmptyString(section.section_id);
    const deliverableId = nonEmptyString(section.deliverable_id);
    if (!sectionId || !deliverableId) return [];
    return [
      {
        ...section,
        section_id: sectionId,
        deliverable_id: deliverableId,
        parent_section_id: nullableString(section.parent_section_id),
        section_index: finiteNonNegativeNumber(section.section_index) ?? 0,
        title: nullableString(section.title),
        prose_text: nullableString(section.prose_text),
        prose_provenance:
          section.prose_provenance &&
          typeof section.prose_provenance === "object" &&
          !Array.isArray(section.prose_provenance)
            ? section.prose_provenance
            : null,
        block_count: finiteNonNegativeNumber(section.block_count) ?? 0,
      },
    ];
  });
}

export function safeDeliverableDetail(
  detail: DeliverableDetailResponse | null | undefined,
): DeliverableDetailResponse | null {
  if (!detail) return null;
  const deliverableId = nonEmptyString(detail.deliverable_id);
  if (!deliverableId) return null;
  return {
    ...detail,
    deliverable_id: deliverableId,
    title: nonEmptyString(detail.title) ?? "Untitled piece",
    deliverable_kind: safeKind(detail.deliverable_kind),
    status: safeStatus(detail.status),
    investigation_root_id: nullableString(detail.investigation_root_id),
    sections: Array.isArray(detail.sections) ? safeSections(detail.sections) : [],
  };
}
