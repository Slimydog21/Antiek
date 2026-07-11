/**
 * WorkstationRecursiveRecordPackPanel - recursive record pack for prompts.
 *
 * Free-file. record_persisted and prompts_injected always false.
 */

import { useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../../components/lemon";
import {
  composeWorkstationRecursiveRecordPack,
  formatWorkstationRecursiveRecordPackSummary,
  type WorkstationRecursiveRecordPack,
} from "../../api/workstationRecursiveRecordPack";

export interface WorkstationRecursiveRecordPackPanelProps {
  composeFn?: typeof composeWorkstationRecursiveRecordPack;
}

export default function WorkstationRecursiveRecordPackPanel({
  composeFn = composeWorkstationRecursiveRecordPack,
}: WorkstationRecursiveRecordPackPanelProps) {
  const [sessionId, setSessionId] = useState("sess-1");
  const [itemsRaw, setItemsRaw] = useState(
    "r1|insight|scaling holds under noise|0.9\nr2|question|what about multimodal?|0.5",
  );
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<WorkstationRecursiveRecordPack | null>(null);

  function onCompose() {
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
          const weight =
            parts[3] !== undefined && parts[3] !== ""
              ? Number(parts[3])
              : undefined;
          return {
            record_id: parts[0],
            kind: parts[1] as
              | "insight"
              | "question"
              | "highlight"
              | "finding"
              | "open_thread",
            text: parts[2],
            weight,
          };
        });
      setResult(
        composeFn({
          session_id: sessionId,
          items,
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div data-testid="workstation-recursive-record-pack-panel">
      <LemonCard
        title="Workstation recursive record pack"
        className="workstation-recursive-record-pack-panel"
      >
        <p className="text-sm opacity-80" data-testid="wrrp-blurb">
          Pack insights, questions, and highlights so they can inform prompts.
          Pure intent — record_persisted and prompts_injected stay false.
        </p>
        <div className="flex flex-col gap-3 mt-3">
          <label className="text-sm flex flex-col gap-1">
            <span>Session id</span>
            <LemonInput
              value={sessionId}
              onChange={(e) => setSessionId(e.target.value)}
              data-testid="wrrp-session"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Items (record_id|kind|text|weight? per line)</span>
            <textarea
              value={itemsRaw}
              onChange={(e) => setItemsRaw(e.target.value)}
              data-testid="wrrp-items"
              className="border border-border rounded px-2 py-1 text-sm min-h-[5rem] font-mono"
            />
          </label>
          <LemonButton
            variant="primary"
            onClick={onCompose}
            data-testid="wrrp-compose"
          >
            Compose record pack
          </LemonButton>
          {error ? (
            <div className="text-sm text-danger" data-testid="wrrp-error">
              {error}
            </div>
          ) : null}
          {result ? (
            <div
              data-testid="wrrp-result"
              className="text-sm flex flex-col gap-1"
            >
              <div data-testid="wrrp-summary">
                {formatWorkstationRecursiveRecordPackSummary(result)}
              </div>
              <div data-testid="wrrp-ready">
                pack_ready={String(result.pack_ready)}
              </div>
              <div data-testid="wrrp-persisted">
                record_persisted={String(result.record_persisted)}
              </div>
              <div data-testid="wrrp-injected">
                prompts_injected={String(result.prompts_injected)}
              </div>
            </div>
          ) : null}
        </div>
      </LemonCard>
    </div>
  );
}
