// SPR-08 / M4 — block dispatch.
//
// Maps block_type → renderer component. The closed-set discipline
// in services/notebooks/blocks.py is enforced here too: an unknown
// block_type renders the UnknownBlock fallback rather than throwing,
// so a single corrupted row doesn't take the whole notebook down.

import type { PerDocBlockProps } from "./types";
import AiQa from "./AiQa";
import CiteLink from "./CiteLink";
import CrossDocJump from "./CrossDocJump";
import HighlightCard from "./HighlightCard";
import Prose from "./Prose";
import VoiceBlock from "./VoiceBlock";

export type BlockComponent = (props: PerDocBlockProps) => JSX.Element;

export const BLOCK_COMPONENTS: Record<string, BlockComponent> = {
  highlight_card: HighlightCard,
  voice_block: VoiceBlock,
  ai_qa: AiQa,
  cite_link: CiteLink,
  cross_doc_jump: CrossDocJump,
  prose: Prose,
};

export function renderBlock(props: PerDocBlockProps): JSX.Element {
  const Component = BLOCK_COMPONENTS[props.block.block_type];
  if (!Component) {
    return (
      <section
        data-block-id={props.block.block_id}
        data-block-type={props.block.block_type}
        className="border border-amber-200 bg-amber-50 rounded-md p-3 text-xs text-amber-800"
      >
        Unknown block type: <code>{props.block.block_type}</code>. This
        likely means the substrate produced a row whose type isn't in
        the closed set — see services/notebooks/blocks.py.
      </section>
    );
  }
  return <Component {...props} />;
}

export {
  AiQa,
  CiteLink,
  CrossDocJump,
  HighlightCard,
  Prose,
  VoiceBlock,
};
