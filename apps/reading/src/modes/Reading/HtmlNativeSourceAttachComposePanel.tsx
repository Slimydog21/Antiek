/**
 * HtmlNativeSourceAttachComposePanel — arxiv/substack HTML attach.
 *
 * Free-file. remote_fetched, pdf_view_authorized, store_mutated always false.
 */

import { useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../../components/lemon";
import {
  composeHtmlNativeSourceAttach,
  formatHtmlNativeSourceAttachSummary,
  type HtmlNativeSourceAttachCompose,
} from "../../api/htmlNativeSourceAttachCompose";

export interface HtmlNativeSourceAttachComposePanelProps {
  composeFn?: typeof composeHtmlNativeSourceAttach;
}

export default function HtmlNativeSourceAttachComposePanel({
  composeFn = composeHtmlNativeSourceAttach,
}: HtmlNativeSourceAttachComposePanelProps) {
  const [sessionId, setSessionId] = useState("ws-1");
  const [parent, setParent] = useState("asset-1");
  const [arxivTitle, setArxivTitle] = useState("Scaling laws paper");
  const [arxivHtml, setArxivHtml] = useState("<article>abstract…</article>");
  const [substackTitle, setSubstackTitle] = useState("Essay on routing");
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<HtmlNativeSourceAttachCompose | null>(null);

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      setResult(
        composeFn({
          session_id: sessionId.trim(),
          parent_asset_id: parent.trim(),
          requested_families: ["arxiv", "substack"],
          operator_ack: ack,
          sources: [
            {
              source_id: "arxiv-1",
              family: "arxiv",
              title: arxivTitle.trim() || "arxiv",
              external_id: "arxiv:2301.00001",
              html_fragment: arxivHtml.trim() || undefined,
            },
            {
              source_id: "substack-1",
              family: "substack",
              title: substackTitle.trim() || "substack",
              url: "https://example.substack.com/p/routing",
            },
          ],
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div data-testid="html-native-source-attach-compose-panel">
      <LemonCard
        title="HTML-native source attach (arxiv · substack)"
        className="html-native-source-attach-compose-panel"
      >
        <p className="text-sm opacity-80" data-testid="hnsac-blurb">
          Attach knowledge-dense HTML sources to a research session. Pure —
          remote_fetched, pdf_view_authorized, and store_mutated stay false.
        </p>
        <div className="flex flex-col gap-2 mt-3">
          <label className="text-sm flex flex-col gap-1">
            <span>Session id</span>
            <LemonInput
              value={sessionId}
              onChange={(e) => setSessionId(e.target.value)}
              data-testid="hnsac-session"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Parent asset</span>
            <LemonInput
              value={parent}
              onChange={(e) => setParent(e.target.value)}
              data-testid="hnsac-parent"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>arXiv title</span>
            <LemonInput
              value={arxivTitle}
              onChange={(e) => setArxivTitle(e.target.value)}
              data-testid="hnsac-arxiv-title"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>arXiv HTML fragment</span>
            <textarea
              value={arxivHtml}
              onChange={(e) => setArxivHtml(e.target.value)}
              data-testid="hnsac-arxiv-html"
              className="border border-border rounded px-2 py-1 text-sm min-h-[3rem]"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Substack title</span>
            <LemonInput
              value={substackTitle}
              onChange={(e) => setSubstackTitle(e.target.value)}
              data-testid="hnsac-substack-title"
            />
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={ack}
              onChange={(e) => setAck(e.target.checked)}
              data-testid="hnsac-ack"
            />
            <span>operator_ack</span>
          </label>
          <LemonButton
            variant="primary"
            onClick={onCompose}
            data-testid="hnsac-compose"
          >
            Compose source attach
          </LemonButton>
          {error ? (
            <p className="text-sm text-danger" data-testid="hnsac-error">
              {error}
            </p>
          ) : null}
          {result ? (
            <div
              className="text-sm flex flex-col gap-1 mt-2"
              data-testid="hnsac-result"
            >
              <div data-testid="hnsac-ready">
                attach_ready={String(result.attach_ready)}
              </div>
              <div data-testid="hnsac-remote">
                remote_fetched={String(result.remote_fetched)}
              </div>
              <div data-testid="hnsac-pdf">
                pdf_view_authorized={String(result.pdf_view_authorized)}
              </div>
              <div data-testid="hnsac-store">
                store_mutated={String(result.store_mutated)}
              </div>
              <div data-testid="hnsac-summary">
                {formatHtmlNativeSourceAttachSummary(result)}
              </div>
            </div>
          ) : null}
        </div>
      </LemonCard>
    </div>
  );
}
