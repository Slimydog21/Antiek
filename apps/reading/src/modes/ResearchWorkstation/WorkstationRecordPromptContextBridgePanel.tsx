/**
 * WorkstationRecordPromptContextBridgePanel - records → proposed prompt.
 *
 * Free-file. prompts_injected and record_persisted always false.
 */

import { useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../../components/lemon";
import {
  bridgeWorkstationRecordPromptContext,
  formatWorkstationRecordPromptContextBridgeSummary,
  type PromptContextEnvelope,
} from "../../api/workstationRecordPromptContextBridge";

export interface WorkstationRecordPromptContextBridgePanelProps {
  bridgeFn?: typeof bridgeWorkstationRecordPromptContext;
}

export default function WorkstationRecordPromptContextBridgePanel({
  bridgeFn = bridgeWorkstationRecordPromptContext,
}: WorkstationRecordPromptContextBridgePanelProps) {
  const [sessionId, setSessionId] = useState("sess-1");
  const [userPrompt, setUserPrompt] = useState(
    "What are the open questions on scaling?",
  );
  const [itemsRaw, setItemsRaw] = useState(
    "r1|insight|scaling holds under noise|0.9\nr2|question|what about multimodal?|0.5",
  );
  const [placement, setPlacement] = useState<"prefix" | "suffix">("prefix");
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<PromptContextEnvelope | null>(null);

  function onBridge() {
    setError(null);
    setResult(null);
    try {
      const items = itemsRaw
        .split(/\r?\n/)
        .map((l) => l.trim())
        .filter(Boolean)
        .map((line, i) => {
          const parts = line.split("|").map((p) => p.trim());
          if (parts.length < 3) {
            throw new Error(
              `line ${i + 1} must be record_id|kind|text|weight?`,
            );
          }
          return {
            record_id: parts[0],
            kind: parts[1] as
              | "insight"
              | "question"
              | "highlight"
              | "finding"
              | "open_thread",
            text: parts[2],
            weight:
              parts[3] !== undefined && parts[3] !== ""
                ? Number(parts[3])
                : undefined,
          };
        });
      setResult(
        bridgeFn({
          session_id: sessionId,
          user_prompt: userPrompt,
          items,
          placement,
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div data-testid="workstation-record-prompt-context-bridge-panel">
      <LemonCard
        title="Record pack → prompt context bridge"
        className="workstation-record-prompt-context-bridge-panel"
      >
        <p className="text-sm opacity-80" data-testid="wrpcb-blurb">
          Bridge recursive workstation records into a proposed prompt envelope
          so insights and questions inform the next prompt. Pure intent —
          prompts_injected stays false.
        </p>
        <div className="flex flex-col gap-3 mt-3">
          <label className="text-sm flex flex-col gap-1">
            <span>Session id</span>
            <LemonInput
              value={sessionId}
              onChange={(e) => setSessionId(e.target.value)}
              data-testid="wrpcb-session"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>User prompt</span>
            <textarea
              value={userPrompt}
              onChange={(e) => setUserPrompt(e.target.value)}
              data-testid="wrpcb-prompt"
              className="border border-border rounded px-2 py-1 text-sm min-h-[3rem]"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Records (record_id|kind|text|weight?)</span>
            <textarea
              value={itemsRaw}
              onChange={(e) => setItemsRaw(e.target.value)}
              data-testid="wrpcb-items"
              className="border border-border rounded px-2 py-1 text-sm min-h-[4rem] font-mono"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Placement</span>
            <select
              value={placement}
              onChange={(e) =>
                setPlacement(e.target.value as "prefix" | "suffix")
              }
              data-testid="wrpcb-placement"
              className="border border-border rounded px-2 py-1 text-sm"
            >
              <option value="prefix">prefix</option>
              <option value="suffix">suffix</option>
            </select>
          </label>
          <LemonButton
            variant="primary"
            onClick={onBridge}
            data-testid="wrpcb-bridge"
          >
            Bridge to proposed prompt
          </LemonButton>
          {error ? (
            <div className="text-sm text-danger" data-testid="wrpcb-error">
              {error}
            </div>
          ) : null}
          {result ? (
            <div
              data-testid="wrpcb-result"
              className="text-sm flex flex-col gap-1"
            >
              <div data-testid="wrpcb-summary">
                {formatWorkstationRecordPromptContextBridgeSummary(result)}
              </div>
              <div data-testid="wrpcb-injected">
                prompts_injected={String(result.prompts_injected)}
              </div>
              <div data-testid="wrpcb-persisted">
                record_persisted={String(result.record_persisted)}
              </div>
              <div data-testid="wrpcb-ready">
                bridge_ready={String(result.bridge_ready)}
              </div>
              <pre
                data-testid="wrpcb-proposed"
                className="text-xs opacity-80 whitespace-pre-wrap border border-border rounded p-2 max-h-40 overflow-auto"
              >
                {result.proposed_prompt}
              </pre>
            </div>
          ) : null}
        </div>
      </LemonCard>
    </div>
  );
}
