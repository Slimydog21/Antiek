// SPR-04 M4 — presentational fragment for the AI reply.
//
// Extracted from AiCommandPalette so the reply rendering can be
// stubbed/replaced in stories and tests without re-mounting the whole
// palette. The sprint spec called for a separate file path for the
// "response overlay"; we keep the file thin so the palette stays the
// single source of truth for the input + submit lifecycle.

export type AiReplyShape = "CHALLENGE" | "SYNTHESIS" | "EXTENSION";

interface AiResponseOverlayProps {
  shape: AiReplyShape;
  text: string;
}

export default function AiResponseOverlay({ shape, text }: AiResponseOverlayProps) {
  return (
    <div
      className="border border-stone-200 rounded p-3 bg-stone-50"
      data-testid="ai-response-overlay"
    >
      <p className="text-[10px] font-mono uppercase tracking-wide text-stone-500 mb-1">
        {shape}
      </p>
      <p className="text-sm text-stone-800 whitespace-pre-wrap font-serif">
        {text}
      </p>
    </div>
  );
}
