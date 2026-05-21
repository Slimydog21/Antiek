// SPR-08 / M4 — cite_link renderer.
//
// Source event: cite_jump. Click → cite-jump via the SPR-07 path
// (?page=&chunk= deep-link the WrestleApp's cite handler already
// understands).

import BlockShell from "./BlockShell";
import type { PerDocBlockProps } from "./types";

interface CiteLinkContent {
  target_document_id?: string | null;
  target_chunk_id?: string | null;
  direction?: string | null;
  source_chunk_id?: string | null;
}

export default function CiteLink(props: PerDocBlockProps): JSX.Element {
  const content = (props.block.content_json as unknown as CiteLinkContent) || {};
  const targetDoc = content.target_document_id;
  const targetChunk = content.target_chunk_id;
  const direction = content.direction || "forward";

  const onClick = () => {
    if (!targetDoc) return;
    if (props.onCiteJump) {
      props.onCiteJump(targetDoc, targetChunk);
    }
  };

  return (
    <BlockShell {...props} typeLabel={`cite · ${direction}`}>
      <button
        type="button"
        onClick={onClick}
        disabled={!targetDoc}
        className={
          "text-left w-full text-blue-700 hover:text-blue-900 hover:underline " +
          "disabled:text-stone-400 disabled:cursor-not-allowed"
        }
        data-testid={`cite-link-${props.block.block_id}`}
      >
        {targetDoc ? (
          <>
            → {targetDoc.slice(-12)}
            {targetChunk && (
              <span className="text-stone-500 ml-1">
                · {targetChunk.slice(-8)}
              </span>
            )}
          </>
        ) : (
          <span className="italic text-stone-500">cite jump (target unresolved)</span>
        )}
      </button>
      {content.source_chunk_id && (
        <p className="mt-1 text-[11px] font-mono text-stone-400">
          from chunk {content.source_chunk_id.slice(-8)}
        </p>
      )}
    </BlockShell>
  );
}
