/**
 * SourcePublicationRegistryPanel - select knowledge-dense source families.
 *
 * Free-file. Never live-fetches arxiv/substack; fetched always false.
 */

import { useState } from "react";
import { LemonButton, LemonCard } from "../../components/lemon";
import {
  formatSourcePackSummary,
  selectPublicationSources,
  type PublicationFamily,
  type SourceSelectionPack,
} from "../../api/sourcePublicationRegistry";

const FAMILIES: PublicationFamily[] = [
  "arxiv",
  "substack",
  "openalex",
  "web",
  "custom",
];

export interface SourcePublicationRegistryPanelProps {
  selectFn?: typeof selectPublicationSources;
}

export default function SourcePublicationRegistryPanel({
  selectFn = selectPublicationSources,
}: SourcePublicationRegistryPanelProps) {
  const [selected, setSelected] = useState<PublicationFamily[]>([
    "arxiv",
    "substack",
  ]);
  const [customId, setCustomId] = useState("");
  const [customLabel, setCustomLabel] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<SourceSelectionPack | null>(null);

  function toggle(family: PublicationFamily) {
    setSelected((prev) =>
      prev.includes(family)
        ? prev.filter((f) => f !== family)
        : [...prev, family],
    );
  }

  function onSelect() {
    setError(null);
    setResult(null);
    try {
      const custom_sources =
        customId.trim() && customLabel.trim()
          ? [
              {
                source_id: customId.trim(),
                family: "custom" as const,
                label: customLabel.trim(),
                enabled: true,
              },
            ]
          : null;
      setResult(
        selectFn({
          requested_families: selected,
          custom_sources,
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div data-testid="source-publication-registry-panel">
      <LemonCard
        title="Source publication registry"
        className="source-publication-registry-panel"
      >
        <p className="text-sm opacity-80" data-testid="spr-blurb">
          Select knowledge-dense publications for deep research (arXiv, Substack,
          OpenAlex, web, custom). Pure selection — fetched stays false.
        </p>
        <div className="flex flex-col gap-3 mt-3">
          <div className="flex flex-wrap gap-3" data-testid="spr-families">
            {FAMILIES.map((f) => (
              <label key={f} className="text-sm flex items-center gap-1">
                <input
                  type="checkbox"
                  checked={selected.includes(f)}
                  onChange={() => toggle(f)}
                  data-testid={`spr-family-${f}`}
                />
                {f}
              </label>
            ))}
          </div>
          <label className="text-sm flex flex-col gap-1">
            <span>Custom source id (optional)</span>
            <input
              className="border border-border rounded px-2 py-1"
              value={customId}
              onChange={(e) => setCustomId(e.target.value)}
              data-testid="spr-custom-id"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Custom source label</span>
            <input
              className="border border-border rounded px-2 py-1"
              value={customLabel}
              onChange={(e) => setCustomLabel(e.target.value)}
              data-testid="spr-custom-label"
            />
          </label>
          <LemonButton
            variant="primary"
            onClick={onSelect}
            data-testid="spr-run"
          >
            Build source pack
          </LemonButton>
          {error ? (
            <div className="text-sm text-danger" data-testid="spr-error">
              {error}
            </div>
          ) : null}
          {result ? (
            <div data-testid="spr-result" className="text-sm flex flex-col gap-1">
              <div data-testid="spr-summary">
                {formatSourcePackSummary(result)}
              </div>
              <div data-testid="spr-fetched">
                fetched={String(result.fetched)}
              </div>
            </div>
          ) : null}
        </div>
      </LemonCard>
    </div>
  );
}
