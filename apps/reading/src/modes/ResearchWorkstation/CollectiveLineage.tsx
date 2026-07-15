import { ExternalLink, GitMerge } from "lucide-react";
import { Link } from "react-router-dom";

import type {
  Event,
  ResearchCompositionProvenance,
} from "../../generated/types";
import { API_BASE } from "../../lib/api";

const COMPOSITION_ID = /^cmp-[0-9a-f]{64}$/;
const INVESTIGATION_ID = /^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$/;
const SHA256 = /^[0-9a-f]{64}$/;

export function collectiveProvenance(
  events: Event[],
  activeInvestigationId: string,
): ResearchCompositionProvenance | null {
  if (!INVESTIGATION_ID.test(activeInvestigationId)) return null;
  const starts = events.filter((event) => {
    if (!isRecord(event) || !isRecord(event.payload)) return false;
    return (
      event.investigation_id === activeInvestigationId &&
      event.action_type === "investigation.start_requested" &&
      event.payload.action_type === "investigation.start_requested" &&
      Number.isInteger(event.schema_version) &&
      Number(event.schema_version) >= 37
    );
  });
  if (starts.length !== 1) return null;
  const payload = starts[0].payload as unknown;
  if (!isRecord(payload)) return null;
  if (
    payload.derived_source != null ||
    payload.evidence_manifest != null ||
    (payload.derived_sources != null &&
      (!Array.isArray(payload.derived_sources) ||
        payload.derived_sources.length > 0))
  )
    return null;
  const provenance = payload.research_composition;
  if (!isRecord(provenance) || !Array.isArray(provenance.members)) return null;
  if (
    typeof provenance.composition_id !== "string" ||
    !COMPOSITION_ID.test(provenance.composition_id) ||
    typeof provenance.ordered_set_digest !== "string" ||
    provenance.composition_id.slice(4) !== provenance.ordered_set_digest ||
    provenance.composition_schema_version !== 1 ||
    !SHA256.test(provenance.ordered_set_digest) ||
    typeof provenance.member_count !== "number" ||
    !Number.isInteger(provenance.member_count) ||
    provenance.member_count < 2 ||
    provenance.member_count > 8 ||
    provenance.members.length !== provenance.member_count
  )
    return null;
  const ids = new Set<string>();
  const members: ResearchCompositionProvenance["members"] = [];
  for (const [ordinal, member] of provenance.members.entries()) {
    if (
      !isRecord(member) ||
      member.ordinal !== ordinal ||
      typeof member.investigation_id !== "string" ||
      !INVESTIGATION_ID.test(member.investigation_id) ||
      typeof member.content_hash !== "string" ||
      !SHA256.test(member.content_hash) ||
      typeof member.rendered_sha256 !== "string" ||
      !SHA256.test(member.rendered_sha256) ||
      ids.has(member.investigation_id)
    )
      return null;
    ids.add(member.investigation_id);
    members.push({
      investigation_id: member.investigation_id,
      content_hash: member.content_hash,
      rendered_sha256: member.rendered_sha256,
      ordinal,
    });
  }
  return {
    composition_id: provenance.composition_id,
    ordered_set_digest: provenance.ordered_set_digest,
    composition_schema_version: 1,
    member_count: provenance.member_count,
    members,
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export default function CollectiveLineage({
  events,
  investigationId,
}: {
  events: Event[];
  investigationId: string;
}) {
  const provenance = collectiveProvenance(events, investigationId);
  if (!provenance) return null;
  const htmlUrl = new URL(
    `${API_BASE}/research/artifacts/compositions/${encodeURIComponent(provenance.composition_id)}`,
    window.location.origin,
  ).toString();

  return (
    <section
      className="border-b border-rule bg-ice-1 px-4 py-3 dark:border-charcoal-1 dark:bg-charcoal-2"
      aria-labelledby="collective-lineage-title"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <GitMerge aria-hidden="true" size={15} />
          <h2
            id="collective-lineage-title"
            className="font-mono text-xs font-semibold uppercase text-shadow-1 dark:text-moonlight"
          >
            Collective sources
          </h2>
          <span className="font-mono text-[10px] text-ink-mute dark:text-moonlight">
            {provenance.member_count}
          </span>
        </div>
        <a
          href={htmlUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 text-xs font-medium text-ink underline decoration-rule underline-offset-2 dark:text-bright"
        >
          Combined HTML <ExternalLink aria-hidden="true" size={13} />
        </a>
      </div>
      <ol className="mt-2 flex flex-wrap gap-x-3 gap-y-1">
        {provenance.members.map((member) => (
          <li key={member.investigation_id}>
            <Link
              to={`/inv/${encodeURIComponent(member.investigation_id)}`}
              className="font-mono text-xs text-ink underline decoration-rule underline-offset-2 dark:text-bright"
            >
              {member.ordinal + 1}. {member.investigation_id}
            </Link>
          </li>
        ))}
      </ol>
    </section>
  );
}
