// SPR-08 / M4 — ai_qa renderer.
//
// Source event: ai_response_accepted. The block joins back to the
// matching ai_prompt_sent for the question text via prompt_id (see
// services/notebooks/auto_populate.py::_content_for_ai_qa).

import BlockShell from "./BlockShell";
import type { PerDocBlockProps } from "./types";

interface AiQaContent {
  prompt_id?: string | null;
  response_id?: string | null;
  accept_kind?: string | null;
  prompt_text?: string | null;
  prompt_missing?: boolean | null;
}

export default function AiQa(props: PerDocBlockProps): JSX.Element {
  const content = (props.block.content_json as unknown as AiQaContent) || {};
  const promptText = (content.prompt_text || "").trim();
  const missing = content.prompt_missing === true;
  const acceptKind = content.accept_kind || "accepted";

  return (
    <BlockShell {...props} typeLabel="ai q&a">
      <div className="space-y-2">
        <div>
          <p className="text-[10px] font-mono text-stone-500 uppercase tracking-wider">
            prompt
          </p>
          {missing ? (
            <p className="text-stone-400 italic text-xs">
              (prompt event not in store — will fill on next populate)
            </p>
          ) : (
            <p className="text-stone-800">
              {promptText || (
                <span className="text-stone-400 italic">(prompt absent)</span>
              )}
            </p>
          )}
        </div>
        <div>
          <p className="text-[10px] font-mono text-stone-500 uppercase tracking-wider">
            response — {acceptKind}
          </p>
          <p className="text-stone-700 text-xs italic">
            (response body lives in the chat history; this block
            records that the operator accepted it)
          </p>
        </div>
      </div>
    </BlockShell>
  );
}
