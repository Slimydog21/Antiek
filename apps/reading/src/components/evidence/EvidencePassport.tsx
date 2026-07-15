export type EvidenceCustody =
  | "source-identified"
  | "hash-reviewed"
  | "restricted"
  | "rights-unconfirmed"
  | "unavailable";

export type EvidencePrecision =
  | "exact-passage"
  | "document-only"
  | "anchor-pending"
  | "artifact-snapshot"
  | "no-anchor";

export interface EvidencePassportView {
  sourceName?: string | null;
  locator?: string | null;
  custody: EvidenceCustody;
  precision: EvidencePrecision;
}

export interface EvidencePassportProps extends EvidencePassportView {
  compact?: boolean;
  className?: string;
}

const CUSTODY_COPY: Record<EvidenceCustody, string> = {
  "source-identified": "Source identified",
  "hash-reviewed": "Snapshot hash reviewed",
  restricted: "Source restricted",
  "rights-unconfirmed": "Rights unconfirmed",
  unavailable: "Source unavailable",
};

const PRECISION_COPY: Record<EvidencePrecision, string> = {
  "exact-passage": "Exact passage anchored",
  "document-only": "Document-level source",
  "anchor-pending": "Exact passage anchor pending",
  "artifact-snapshot": "Research snapshot",
  "no-anchor": "No source anchor",
};

/**
 * EvidencePassport is presentation-only. Hosts supply already-authoritative
 * facts; this component performs no fetch and never infers precision from an
 * identifier. In particular, a reviewed snapshot hash does not imply claim
 * correctness, and a known document does not imply an exact passage anchor.
 */
export default function EvidencePassport({
  sourceName,
  locator,
  custody,
  precision,
  compact = false,
  className = "",
}: EvidencePassportProps) {
  return (
    <dl
      data-evidence-passport=""
      data-custody={custody}
      data-precision={precision}
      className={[
        "grid min-w-0 gap-x-3 gap-y-1 border-l-4 border-sun bg-ice-1/95 text-ink dark:bg-charcoal-1 dark:text-bright",
        compact
          ? "grid-cols-[minmax(0,1fr)_auto] px-2.5 py-2 text-[10px]"
          : "grid-cols-2 rounded-r-md px-3 py-2.5 text-[11px] shadow-z1",
        className,
      ]
        .filter(Boolean)
        .join(" ")}
    >
      <PassportFact
        label="Source"
        value={sourceName?.trim() || "Source name unavailable"}
      />
      {locator ? <PassportFact label="Locator" value={locator} /> : null}
      <PassportFact label="Custody" value={CUSTODY_COPY[custody]} />
      <PassportFact label="Precision" value={PRECISION_COPY[precision]} />
    </dl>
  );
}

function PassportFact({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <dt className="font-mono uppercase tracking-[0.12em] text-shadow-1 dark:text-moonlight">
        {label}
      </dt>
      <dd className="truncate font-medium" title={value}>
        {value}
      </dd>
    </div>
  );
}
