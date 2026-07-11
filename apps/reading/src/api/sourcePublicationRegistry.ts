/**
 * Knowledge-dense publication registry for deep research (pure client).
 *
 * Operator vision: reference arxiv, substack, and other knowledge-dense
 * publications when running deep research. This pure layer catalogs known
 * source families and builds a selection pack — never invents live fetch hits.
 *
 * fetched is always false here (selection / policy only).
 */

export type PublicationFamily =
  | "arxiv"
  | "substack"
  | "openalex"
  | "web"
  | "custom";

export interface PublicationSource {
  source_id: string;
  family: PublicationFamily;
  label: string;
  /** Optional base URL pattern or host. */
  host?: string;
  enabled: boolean;
}

export interface SourceSelectionInput {
  /** Source families the operator wants available for this research. */
  requested_families: PublicationFamily[];
  /** Optional custom sources (family=custom). */
  custom_sources?: PublicationSource[] | null;
  /** When true, only enabled catalog entries + customs. */
  enabled_only?: boolean;
}

export interface SourceSelectionPack {
  sources: PublicationSource[];
  families: PublicationFamily[];
  /** Always false — pure selection does not fetch publications. */
  fetched: false;
  notes: string[];
  authority: "source_publication_registry_advisory";
}

/** Built-in knowledge-dense families (catalog only — no live probe). */
export const DEFAULT_PUBLICATION_CATALOG: readonly PublicationSource[] = [
  {
    source_id: "arxiv",
    family: "arxiv",
    label: "arXiv",
    host: "arxiv.org",
    enabled: true,
  },
  {
    source_id: "substack",
    family: "substack",
    label: "Substack",
    host: "substack.com",
    enabled: true,
  },
  {
    source_id: "openalex",
    family: "openalex",
    label: "OpenAlex",
    host: "openalex.org",
    enabled: true,
  },
  {
    source_id: "web",
    family: "web",
    label: "General web",
    enabled: true,
  },
] as const;

function requireFamily(value: unknown, name: string): PublicationFamily {
  if (
    value !== "arxiv" &&
    value !== "substack" &&
    value !== "openalex" &&
    value !== "web" &&
    value !== "custom"
  ) {
    throw new Error(
      `${name} must be arxiv|substack|openalex|web|custom`,
    );
  }
  return value;
}

/**
 * Build a source selection pack from requested families + optional customs.
 * Never invents live fetch results (fetched always false).
 */
export function selectPublicationSources(
  input: SourceSelectionInput,
  catalog: readonly PublicationSource[] = DEFAULT_PUBLICATION_CATALOG,
): SourceSelectionPack {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (!Array.isArray(input.requested_families)) {
    throw new Error("requested_families must be an array");
  }
  if (input.requested_families.length === 0) {
    throw new Error("requested_families must be non-empty");
  }

  const notes: string[] = [
    "fetched=false — selection pack only (no live arxiv/substack/web fetch)",
  ];
  const enabledOnly = input.enabled_only !== false;
  const requested = new Set<PublicationFamily>();
  for (let i = 0; i < input.requested_families.length; i++) {
    requested.add(
      requireFamily(input.requested_families[i], `requested_families[${i}]`),
    );
  }

  const sources: PublicationSource[] = [];
  for (const entry of catalog) {
    if (!requested.has(entry.family)) continue;
    if (enabledOnly && !entry.enabled) {
      notes.push(`catalog ${entry.source_id} skipped (disabled)`);
      continue;
    }
    sources.push({ ...entry });
  }

  if (input.custom_sources != null) {
    if (!Array.isArray(input.custom_sources)) {
      throw new Error("custom_sources must be an array or null");
    }
    for (let i = 0; i < input.custom_sources.length; i++) {
      const c = input.custom_sources[i];
      if (!c || typeof c !== "object") {
        throw new Error(`custom_sources[${i}] must be an object`);
      }
      const family = requireFamily(c.family, `custom_sources[${i}].family`);
      if (family !== "custom") {
        throw new Error(
          `custom_sources[${i}].family must be custom (use catalog for built-ins)`,
        );
      }
      if (typeof c.source_id !== "string" || !c.source_id.trim()) {
        throw new Error(`custom_sources[${i}].source_id required`);
      }
      if (typeof c.label !== "string" || !c.label.trim()) {
        throw new Error(`custom_sources[${i}].label required`);
      }
      if (typeof c.enabled !== "boolean") {
        throw new Error(`custom_sources[${i}].enabled must be boolean`);
      }
      if (enabledOnly && !c.enabled) {
        notes.push(`custom ${c.source_id} skipped (disabled)`);
        continue;
      }
      if (!requested.has("custom")) {
        notes.push(
          `custom ${c.source_id} skipped (custom not in requested_families)`,
        );
        continue;
      }
      sources.push({
        source_id: c.source_id.trim(),
        family: "custom",
        label: c.label.trim(),
        host: typeof c.host === "string" ? c.host : undefined,
        enabled: c.enabled,
      });
    }
  }

  const families = [...new Set(sources.map((s) => s.family))];
  notes.push(`selected=${sources.length} sources across ${families.length} families`);
  notes.push("fetched=false");

  return {
    sources,
    families,
    fetched: false,
    notes,
    authority: "source_publication_registry_advisory",
  };
}

export function formatSourcePackSummary(pack: SourceSelectionPack): string {
  return (
    `sources=${pack.sources.length} · families=${pack.families.join(",") || "none"} · ` +
    `fetched=false`
  );
}
