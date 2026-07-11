/**
 * Deep research source citation pack (pure).
 *
 * Operator vision: reference arxiv, substack, and other knowledge-dense
 * publications in deep research — highest quality DR product. This pure layer
 * builds a citation pack from operator-supplied citation records and selected
 * source families. Never invents citation metadata or remote fetches.
 *
 * remote_fetched is always false.
 */

import {
  DEFAULT_PUBLICATION_CATALOG,
  selectPublicationSources,
  type PublicationFamily,
  type SourceSelectionPack,
} from "./sourcePublicationRegistry";

export type CitationFamily = PublicationFamily;

export interface CitationRecord {
  citation_id: string;
  family: CitationFamily;
  /** Operator-supplied title (never invented). */
  title: string;
  /** Optional stable external id (e.g. arxiv:2301.00001). */
  external_id?: string;
  /** Optional URL — caller-supplied only. */
  url?: string;
  /** Optional year. */
  year?: number | null;
  /** Optional authors string. */
  authors?: string | null;
}

export interface DeepResearchSourceCitationPackInput {
  session_id: string;
  /** Families to include for this research (arxiv, substack, …). */
  requested_families: CitationFamily[];
  /** Operator-supplied citation rows only. */
  citations: CitationRecord[];
  /** When true, drop citations whose family is not in the selection pack. */
  filter_to_selected_families?: boolean;
}

export interface DeepResearchSourceCitationPack {
  session_id: string;
  selection: SourceSelectionPack;
  citations: CitationRecord[];
  citation_count: number;
  families_present: CitationFamily[];
  /** True when ≥1 citation and ≥1 selected family. */
  pack_ready: boolean;
  /** Always false — pure pack never fetches remote publications. */
  remote_fetched: false;
  notes: string[];
  authority: "deep_research_source_citation_pack_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

const VALID_FAMILIES = new Set<CitationFamily>([
  "arxiv",
  "substack",
  "openalex",
  "web",
  "custom",
]);

/**
 * Build a deep-research citation pack from selection + operator citations.
 * Never invents citation rows; never remote-fetches.
 */
export function buildDeepResearchSourceCitationPack(
  input: DeepResearchSourceCitationPackInput,
): DeepResearchSourceCitationPack {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  const session_id = requireNonEmpty(input.session_id, "session_id");
  if (!Array.isArray(input.requested_families)) {
    throw new Error("requested_families must be an array");
  }
  if (!Array.isArray(input.citations)) {
    throw new Error("citations must be an array");
  }

  const notes: string[] = [
    "remote_fetched=false — citation pack is selection + caller records only",
    "citation rows are operator-supplied only (no invent / no scrape)",
  ];

  const selection = selectPublicationSources({
    requested_families: input.requested_families,
    enabled_only: true,
  });
  notes.push(...selection.notes);
  notes.push(`selected_families=${selection.families.join(",") || "(none)"}`);

  const selectedFamilySet = new Set(selection.families);
  const filter =
    input.filter_to_selected_families === undefined
      ? true
      : input.filter_to_selected_families;
  if (typeof filter !== "boolean") {
    throw new Error("filter_to_selected_families must be boolean when set");
  }

  const seen = new Set<string>();
  const citations: CitationRecord[] = [];
  const families_present = new Set<CitationFamily>();

  for (let i = 0; i < input.citations.length; i++) {
    const c = input.citations[i];
    if (!c || typeof c !== "object") {
      throw new Error(`citations[${i}] must be an object`);
    }
    const citation_id = requireNonEmpty(
      c.citation_id,
      `citations[${i}].citation_id`,
    );
    if (seen.has(citation_id)) {
      throw new Error(`duplicate citation_id: ${citation_id}`);
    }
    seen.add(citation_id);

    const family = c.family;
    if (!VALID_FAMILIES.has(family as CitationFamily)) {
      throw new Error(
        `citations[${i}].family must be arxiv|substack|openalex|web|custom`,
      );
    }
    const fam = family as CitationFamily;
    if (filter && selectedFamilySet.size > 0 && !selectedFamilySet.has(fam)) {
      notes.push(
        `citations[${i}] family=${fam} filtered out (not in selected families)`,
      );
      continue;
    }
    if (filter && selectedFamilySet.size === 0) {
      notes.push(
        `citations[${i}] dropped — no families selected (filter_to_selected_families)`,
      );
      continue;
    }

    const title = requireNonEmpty(c.title, `citations[${i}].title`);
    let external_id: string | undefined;
    if (c.external_id != null) {
      external_id = requireNonEmpty(
        c.external_id,
        `citations[${i}].external_id`,
      );
    }
    let url: string | undefined;
    if (c.url != null) {
      url = requireNonEmpty(c.url, `citations[${i}].url`);
      // Lightweight shape check — not a live fetch.
      if (!/^https?:\/\//i.test(url) && !url.startsWith("arxiv:")) {
        throw new Error(
          `citations[${i}].url must be http(s) URL or arxiv: id when set`,
        );
      }
    }
    let year: number | null | undefined = c.year;
    if (year !== undefined && year !== null) {
      if (
        typeof year !== "number" ||
        !Number.isInteger(year) ||
        year < 1000 ||
        year > 3000
      ) {
        throw new Error(
          `citations[${i}].year must be integer year in [1000,3000] when set`,
        );
      }
    }
    let authors: string | null | undefined = c.authors;
    if (authors !== undefined && authors !== null) {
      if (typeof authors !== "string" || !authors.trim()) {
        throw new Error(
          `citations[${i}].authors must be non-empty string when set`,
        );
      }
      authors = authors.trim();
    }

    citations.push({
      citation_id,
      family: fam,
      title,
      ...(external_id !== undefined ? { external_id } : {}),
      ...(url !== undefined ? { url } : {}),
      ...(year !== undefined ? { year } : {}),
      ...(authors !== undefined ? { authors } : {}),
    });
    families_present.add(fam);
  }

  if (input.citations.length === 0) {
    notes.push("no citations supplied — empty pack (no invent citations)");
  } else {
    notes.push(
      `citations_accepted=${citations.length} of ${input.citations.length} supplied`,
    );
  }

  const pack_ready =
    selection.families.length >= 1 && citations.length >= 1;
  if (!pack_ready) {
    if (selection.families.length < 1) {
      notes.push("pack_ready=false — need ≥1 selected publication family");
    } else {
      notes.push("pack_ready=false — need ≥1 accepted citation");
    }
  } else {
    notes.push(
      `pack_ready=true · citations=${citations.length} · families=${[...families_present].join(",")}`,
    );
  }
  notes.push("remote_fetched=false");

  // Ensure selection still reports fetched=false
  if (selection.fetched !== false) {
    throw new Error("selection.fetched must be false");
  }

  return {
    session_id,
    selection,
    citations,
    citation_count: citations.length,
    families_present: [...families_present],
    pack_ready,
    remote_fetched: false,
    notes,
    authority: "deep_research_source_citation_pack_advisory",
  };
}

export function formatDeepResearchSourceCitationPackSummary(
  p: DeepResearchSourceCitationPack,
): string {
  return (
    `citation pack · n=${p.citation_count} · ready=${p.pack_ready} · ` +
    `remote_fetched=false · families=${p.families_present.join(",") || "none"}`
  );
}

export { DEFAULT_PUBLICATION_CATALOG };
