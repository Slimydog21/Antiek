/**
 * MarketplaceBookHostComposePanel - free-copy → purchase → HTML host compose.
 *
 * Free-file Library panel. Never executes purchase or hosts bytes.
 */

import { useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../../components/lemon";
import {
  composeMarketplaceBookHost,
  formatMarketplaceComposeSummary,
  type MarketplaceBookHostComposeDecision,
} from "../../api/marketplaceBookHostCompose";

export interface MarketplaceBookHostComposePanelProps {
  composeFn?: typeof composeMarketplaceBookHost;
  initialTitle?: string;
}

export default function MarketplaceBookHostComposePanel({
  composeFn = composeMarketplaceBookHost,
  initialTitle = "",
}: MarketplaceBookHostComposePanelProps) {
  const [title, setTitle] = useState(initialTitle);
  const [freeMode, setFreeMode] = useState<"true" | "false" | "null">("false");
  const [sha, setSha] = useState("");
  const [hostRequested, setHostRequested] = useState(true);
  const [skipFree, setSkipFree] = useState(false);
  const [skipAck, setSkipAck] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<MarketplaceBookHostComposeDecision | null>(null);

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      const free_copy_available =
        freeMode === "null" ? null : freeMode === "true";
      setResult(
        composeFn({
          title: title.trim(),
          free_copy_available,
          skip_free_copy: skipFree,
          operator_skip_acknowledged: skipAck,
          html_projection_sha: sha.trim() || null,
          host_requested: hostRequested,
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div data-testid="marketplace-book-host-compose-panel">
      <LemonCard
        title="Marketplace free-copy → HTML host"
        className="marketplace-book-host-compose-panel"
      >
        <p className="text-sm opacity-80" data-testid="mbhc-blurb">
          Free-before-buy, then HTML host after ready projection. Pure compose —
          purchase_executed and hosted stay false.
        </p>
        <div className="flex flex-col gap-3 mt-3">
          <label className="text-sm flex flex-col gap-1">
            <span>Title</span>
            <LemonInput
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              data-testid="mbhc-title"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Free copy available</span>
            <select
              value={freeMode}
              onChange={(e) =>
                setFreeMode(e.target.value as "true" | "false" | "null")
              }
              data-testid="mbhc-free"
              className="border border-border rounded px-2 py-1"
            >
              <option value="false">false (miss)</option>
              <option value="true">true (hit)</option>
              <option value="null">null (unknown)</option>
            </select>
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>HTML projection sha (blank = not ready)</span>
            <LemonInput
              value={sha}
              onChange={(e) => setSha(e.target.value)}
              data-testid="mbhc-sha"
            />
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={hostRequested}
              onChange={(e) => setHostRequested(e.target.checked)}
              data-testid="mbhc-host"
            />
            host_requested
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={skipFree}
              onChange={(e) => setSkipFree(e.target.checked)}
              data-testid="mbhc-skip"
            />
            skip_free_copy
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={skipAck}
              onChange={(e) => setSkipAck(e.target.checked)}
              data-testid="mbhc-skip-ack"
            />
            operator_skip_acknowledged
          </label>
          <LemonButton
            variant="primary"
            onClick={onCompose}
            data-testid="mbhc-run"
          >
            Compose marketplace path
          </LemonButton>
          {error ? (
            <div className="text-sm text-danger" data-testid="mbhc-error">
              {error}
            </div>
          ) : null}
          {result ? (
            <div data-testid="mbhc-result" className="text-sm flex flex-col gap-1">
              <div data-testid="mbhc-summary">
                {formatMarketplaceComposeSummary(result)}
              </div>
              <div data-testid="mbhc-path">path={result.path}</div>
              <div data-testid="mbhc-purchase">
                purchase_executed={String(result.purchase_executed)}
              </div>
              <div data-testid="mbhc-hosted">
                hosted={String(result.hosted)}
              </div>
            </div>
          ) : null}
        </div>
      </LemonCard>
    </div>
  );
}
