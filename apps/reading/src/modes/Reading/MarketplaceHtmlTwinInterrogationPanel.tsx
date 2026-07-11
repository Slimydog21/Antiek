/**
 * MarketplaceHtmlTwinInterrogationPanel — book HTML+twin → interrogate.
 *
 * Free-file. purchase/charge/pdf/dispatch always false.
 */

import { useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../../components/lemon";
import {
  composeMarketplaceHtmlTwinInterrogation,
  formatMarketplaceHtmlTwinInterrogationSummary,
  type MarketplaceHtmlTwinInterrogationCompose,
} from "../../api/marketplaceHtmlTwinInterrogationCompose";

export interface MarketplaceHtmlTwinInterrogationPanelProps {
  composeFn?: typeof composeMarketplaceHtmlTwinInterrogation;
}

export default function MarketplaceHtmlTwinInterrogationPanel({
  composeFn = composeMarketplaceHtmlTwinInterrogation,
}: MarketplaceHtmlTwinInterrogationPanelProps) {
  const [title, setTitle] = useState("Deep Learning Book");
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<MarketplaceHtmlTwinInterrogationCompose | null>(null);

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      setResult(
        composeFn({
          session_id: "sess-demo",
          asset_id: "book-demo",
          title: title.trim() || "Book",
          account_id: "acct-demo",
          free_copy_available: true,
          free_html_projection_sha: "sha-free-demo",
          port_requested: true,
          purchase_ack: false,
          list_price_usd: null,
          approved_spend_usd: null,
          remaining_budget_usd: null,
          operator_ack: ack,
          view_requested: true,
          include_twin_feed: true,
          include_interrogation: true,
          questions: [
            {
              question_id: "q1",
              body: "What is the core thesis?",
              priority: 2,
            },
            {
              question_id: "q2",
              body: "Which claims need evidence?",
              priority: 1,
            },
          ],
          chase_mode: "swarm_fanout",
          models: [
            { model_id: "gpt-5.5", projected_cost_usd_high: 0.4 },
            { model_id: "grok-4.5", projected_cost_usd_high: 0.2 },
          ],
          selected_model_id: "gpt-5.5",
          daily_cap_usd: 25,
          spent_usd: 2,
          projected_cost_usd_high: 0.4,
          would_exceed: false,
          source_families: ["arxiv", "web"],
          user_prompt: "Interrogate this hosted HTML book",
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div data-testid="marketplace-html-twin-interrogation-panel">
      <LemonCard
        title="Reading · marketplace HTML+twin → interrogate"
        className="marketplace-html-twin-interrogation-panel"
      >
        <p className="text-sm opacity-80" data-testid="mhti-blurb">
          Host a free or paid book as HTML with twin substrate, then chase
          questions in the research workstation. Pure — never charges or
          dispatches.
        </p>
        <div className="flex flex-col gap-2 mt-3">
          <label className="text-sm flex flex-col gap-1">
            <span>Title</span>
            <LemonInput
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              data-testid="mhti-title"
            />
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={ack}
              onChange={(e) => setAck(e.target.checked)}
              data-testid="mhti-ack"
            />
            <span>operator_ack</span>
          </label>
          <LemonButton
            type="primary"
            onClick={onCompose}
            data-testid="mhti-compose"
          >
            Compose market → twin → interrogate
          </LemonButton>
        </div>
        {error && (
          <p className="text-sm text-danger mt-2" data-testid="mhti-error">
            {error}
          </p>
        )}
        {result && (
          <div className="mt-3 text-sm" data-testid="mhti-result">
            <p data-testid="mhti-summary">
              {formatMarketplaceHtmlTwinInterrogationSummary(result)}
            </p>
            <ul className="list-disc pl-5 mt-1 opacity-80">
              <li>pack_ready={String(result.pack_ready)}</li>
              <li>
                market_session={String(result.market_twin.session_ready)}
              </li>
              <li>
                loop_ready=
                {String(result.interrogation?.loop_ready ?? false)}
              </li>
              <li>pdf_view_authorized={String(result.pdf_view_authorized)}</li>
              <li>live_dispatched={String(result.live_dispatched)}</li>
            </ul>
          </div>
        )}
      </LemonCard>
    </div>
  );
}
