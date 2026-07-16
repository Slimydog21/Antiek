import { Node, mergeAttributes } from "@tiptap/core";
import { ReactNodeViewRenderer, NodeViewWrapper } from "@tiptap/react";
import type { NodeViewProps } from "@tiptap/react";
import { stringAttr } from "./attrHelpers";

import LemonCard from "../../../components/lemon/LemonCard";

import { emitWernerExperience } from "../../../werner/reactionBus";
/**
 * Chat-exchange block — captures one user-question + assistant-reply
 * turn from the chat panel. Substrate-ref by exchange id; the rendered
 * form is two bubbles + an optional grounding pill.
 */
function ChatExchangeNodeView({ node, deleteNode }: NodeViewProps) {
  const userText = (node.attrs.user_text as string | null) ?? "";
  const assistantText = (node.attrs.assistant_text as string | null) ?? "";
  const exchangeId = (node.attrs.exchange_id as string | null) ?? "(unset)";
  return (
    <NodeViewWrapper className="my-3" data-block="chat-exchange">
      <LemonCard
        elevation="z1"
        colour="glacial"
        title={
          <span className="flex items-center justify-between">
            <span>Chat · {exchangeId.slice(0, 12)}</span>
            <button
              type="button"
              onClick={() => { emitWernerExperience("note_saved"); deleteNode(); }}
              aria-label="Remove block"
              className="font-sans normal-case tracking-normal text-[11px] text-ink-mute dark:text-moonlight hover:text-emperor"
            >
              ✕
            </button>
          </span>
        }
      >
        <div className="space-y-2">
          {userText && (
            <div>
              <span className="font-mono text-[10px] uppercase tracking-wider text-ink-mute dark:text-moonlight">
                you
              </span>
              <p className="font-serif text-[14px] leading-relaxed text-ink dark:text-bright">
                {userText}
              </p>
            </div>
          )}
          {assistantText && (
            <div className="pl-3 border-l-2 border-sun">
              <span className="font-mono text-[10px] uppercase tracking-wider text-sun-deep dark:text-sun">
                ai
              </span>
              <p className="font-serif text-[14px] leading-relaxed text-ink dark:text-bright">
                {assistantText}
              </p>
            </div>
          )}
          {!userText && !assistantText && (
            <p className="text-ink-mute dark:text-moonlight italic font-mono text-[12px]">
              (empty exchange — substrate-ref pending resolve)
            </p>
          )}
        </div>
      </LemonCard>
    </NodeViewWrapper>
  );
}

export const ChatExchangeBlock = Node.create({
  name: "chatExchange",
  group: "block",
  atom: true,
  draggable: true,
  addAttributes() {
    return {
      exchange_id: stringAttr("exchange_id"),
      user_text: stringAttr("user_text"),
      assistant_text: stringAttr("assistant_text"),
    };
  },
  parseHTML() {
    return [{ tag: "antiek-chat-exchange" }];
  },
  renderHTML({ HTMLAttributes }) {
    return ["antiek-chat-exchange", mergeAttributes(HTMLAttributes)];
  },
  addNodeView() {
    return ReactNodeViewRenderer(ChatExchangeNodeView);
  },
});

export default ChatExchangeBlock;
