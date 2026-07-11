/**
 * DeepResearchSourceCitationPackPanel - arxiv/substack citation pack for DR.
 *
 * Free-file. remote_fetched always false.
 */

import { useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../../components/lemon";
import {
  buildDeepResearchSourceCitationPack,
  formatDeepResearchSourceCitationPackSummary,
  type DeepResearchSourceCitationPack,
} from "../../api/deepResearchSourceCitationPack";
import type { PublicationFamily } from "../../api/sourcePublicationRegistry";

export interface DeepResearchSourceCitationPackPanelProps {
  buildFn?: typeof buildDeepResearchSourceCitationPack;
}

export default function DeepResearchSourceCitationPackPanel({
  buildFn = buildDeepResearchSourceCitationPack,
}: DeepResearchSourceCitationPackPanelProps) {
  const [sessionId, setSessionId] = useState("sess-1");
  const [familiesRaw, setFamiliesRaw] = useState("arxiv,substack");
  const [citationsRaw, setCitationsRaw] = useState(
    "c1|arxiv|Attention Is All You Need|arxiv:1706.03762|https://arxiv.org/abs/1706.03762\nc2|substack|Scaling notes||https://example.substack.com/p/scaling",
  );
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<DeepResearchSourceCitationPack | null>(null);

  function onBuild() {
    setError(null);
    setResult(null);
    try {
      const requested_families = familiesRaw
        .split(/[,\s]+/)
        .map((s) => s.trim())
        .filter(Boolean) as PublicationFamily[];
      const citations = citationsRaw
        .split(/\r?\n/)
        .map((l) => l.trim())
        .filter(Boolean)
        .map((line, i) => {
          const parts = line.split("|").map((p) => p.trim());
          if (parts.length < 3) {
            throw new Error(
              `line ${i + 1} must be citation_id|family|title|external_id?|url?`,
            );
          }
          return {
            citation_id: parts[0],
            family: parts[1] as PublicationFamily,
            title: parts[2],
            external_id: parts[3] || undefined,
            url: parts[4] || undefined,
          };
        });
      setResult(
        buildFn({
          session_id: sessionId,
          requested_families,
          citations,
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div data-testid="deep-research-source-citation-pack-panel">
      <LemonCard
        title="Deep research source citation pack"
        className="deep-research-source-citation-pack-panel"
      >
        <p className="text-sm opacity-80" data-testid="drscp-blurb">
          Pack arXiv, Substack, and other knowledge-dense citations for deep
          research. Pure selection + caller records — remote_fetched stays
          false.
        </p>
        <div className="flex flex-col gap-3 mt-3">
          <label className="text-sm flex flex-col gap-1">
            <span>Session id</span>
            <LemonInput
              value={sessionId}
              onChange={(e) => setSessionId(e.target.value)}
              data-testid="drscp-session"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Requested families (comma-separated)</span>
            <LemonInput
              value={familiesRaw}
              onChange={(e) => setFamiliesRaw(e.target.value)}
              data-testid="drscp-families"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>
              Citations (citation_id|family|title|external_id?|url?)
            </span>
            <textarea
              value={citationsRaw}
              onChange={(e) => setCitationsRaw(e.target.value)}
              data-testid="drscp-citations"
              className="border border-border rounded px-2 py-1 text-sm min-h-[5rem] font-mono"
            />
          </label>
          <LemonButton
            variant="primary"
            onClick={onBuild}
            data-testid="drscp-build"
          >
            Build citation pack
          </LemonButton>
          {error ? (
            <div className="text-sm text-danger" data-testid="drscp-error">
              {error}
            </div>
          ) : null}
          {result ? (
            <div
              data-testid="drscp-result"
              className="text-sm flex flex-col gap-1"
            >
              <div data-testid="drscp-summary">
                {formatDeepResearchSourceCitationPackSummary(result)}
              </div>
              <div data-testid="drscp-fetched">
                remote_fetched={String(result.remote_fetched)}
              </div>
              <div data-testid="drscp-ready">
                pack_ready={String(result.pack_ready)}
              </div>
              <div data-testid="drscp-count">
                citation_count={result.citation_count}
              </div>
            </div>
          ) : null}
        </div>
      </LemonCard>
    </div>
  );
}
