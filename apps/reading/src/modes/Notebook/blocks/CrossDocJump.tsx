// SPR-08 / M4 — cross_doc_jump renderer.
//
// Source event: cross_doc_link_clicked (NOT cross_doc_link_surfaced;
// the populator filters to clicked-only — surface-but-no-click is
// negative signal and doesn't merit a block).

import BlockShell from "./BlockShell";
import type { PerDocBlockProps } from "./types";

interface CrossDocContent {
  link_id?: string | null;
  target_document_id?: string | null;
  target_chunk_id?: string | null;
  elapsed_since_surfaced_s?: number | null;
}

export default function CrossDocJump(props: PerDocBlockProps): JSX.Element {
  const content = (props.block.content_json as unknown as CrossDocContent) || {};
  const target = content.target_document_id;
  const elapsed = content.elapsed_since_surfaced_s;

  const onClick = () => {
    if (target && props.onCiteJump) {
      props.onCiteJump(target, content.target_chunk_id);
    }
  };

  return (
    <BlockShell {...props} typeLabel="cross-doc">
      <button
        type="button"
        onClick={onClick}
        disabled={!target}
        className={
          "text-left w-full text-emerald-700 hover:text-emerald-900 " +
          "hover:underline disabled:text-stone-400 " +
          "disabled:cursor-not-allowed"
        }
        data-testid={`cross-doc-${props.block.block_id}`}
      >
        {target ? (
          <>
            ↗ jump to {target.slice(-12)}
            {content.target_chunk_id && (
              <span className="text-stone-500 ml-1">
                · {content.target_chunk_id.slice(-8)}
              </span>
            )}
          </>
        ) : (
          <span className="italic text-stone-500">
            cross-doc link (target unresolved)
          </span>
        )}
      </button>
      {typeof elapsed === "number" && (
        <p className="mt-1 text-[11px] font-mono text-stone-400">
          clicked {elapsed.toFixed(1)}s after surfacing
        </p>
      )}
    </BlockShell>
  );
}
