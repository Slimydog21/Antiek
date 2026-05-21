// SPR-08 / M4 — voice_block renderer.
//
// Source event: voice_note_recorded. Shows duration + an inline
// playback affordance that defers to the SPR-05 playback component
// when wired; until then onVoicePlay is a console breadcrumb.

import BlockShell from "./BlockShell";
import type { PerDocBlockProps } from "./types";

interface VoiceContent {
  voice_note_id?: string | null;
  duration_s?: number | null;
  transcript_present?: boolean | null;
  anchored_to_highlight_id?: string | null;
}

export default function VoiceBlock(props: PerDocBlockProps): JSX.Element {
  const content = (props.block.content_json as unknown as VoiceContent) || {};
  const voiceId = content.voice_note_id || null;
  const duration = content.duration_s;
  const anchorId = content.anchored_to_highlight_id;

  const onPlay = () => {
    if (!voiceId) return;
    if (props.onVoicePlay) {
      props.onVoicePlay(voiceId);
    } else {
      // Sprint 18 dogfood breadcrumb until SPR-05's playback component lands.
      // eslint-disable-next-line no-console
      console.info("[antiek/notebook] voice playback requested:", voiceId);
    }
  };

  return (
    <BlockShell {...props} typeLabel="voice">
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={onPlay}
          aria-label="play voice note"
          disabled={!voiceId}
          className={
            "h-9 w-9 rounded-full bg-stone-900 text-white text-sm " +
            "flex items-center justify-center disabled:bg-stone-300 " +
            "hover:bg-stone-700 transition-colors"
          }
          data-testid={`voice-play-${props.block.block_id}`}
        >
          ▶
        </button>
        <div className="text-sm">
          <p className="font-mono text-stone-600">
            voice note
            {typeof duration === "number" && (
              <span className="ml-2 text-stone-400">
                {duration.toFixed(1)}s
              </span>
            )}
          </p>
          {anchorId && (
            <p className="text-[11px] font-mono text-stone-400">
              anchored to highlight {anchorId.slice(-8)}
            </p>
          )}
          {content.transcript_present === false && (
            <p className="text-[11px] italic text-stone-400">
              transcript pending
            </p>
          )}
        </div>
      </div>
    </BlockShell>
  );
}
