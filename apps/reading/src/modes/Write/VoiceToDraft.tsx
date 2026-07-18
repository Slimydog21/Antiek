import { useCallback, useState } from "react";

import LemonButton from "../../components/lemon/LemonButton";
import { useVoiceCapture } from "../../hooks/useVoiceCapture";
import { emitWernerExperience } from "../../werner/reactionBus";
import { placeBlock } from "./writeApi";

/**
 * VoiceToDraft — speak an idea into the draft, user-sourced (Write SPR-09 M4).
 *
 * "Voice input drafts ideas, labeled user-sourced (§9), persisted." Voice-in is
 * HUMAN speech, never model output. The capture pins `source_kind: "user"`
 * (useVoiceCapture, the VOICE_CAPTURED event) and the resulting transcript is
 * persisted as a USER-AUTHORED OutlineBlock — `provenance_kind:
 * "user_authored"`, which carries NO node_id (no fabricated citation) and is
 * surfaced to the writer with a "yours" provenance label.
 *
 * ════════════════════════════════════════════════════════════════════════
 * §9 LOAD-BEARING INVARIANT — do not "simplify" a voice note into model output
 * ════════════════════════════════════════════════════════════════════════
 * A voice draft is recorded as a `user_authored` block, NOT a `synthesized`
 * one. A future maintainer must NOT route this through the generation/synthesis
 * path or relabel it as model-produced: the operator spoke it, so it is theirs
 * in the graph (the same §9 rule the FloatMenu NOTE follows). The
 * useVoiceCapture hook persists the VOICE_CAPTURED event with `source_kind
 * "user"` PINNED; this block write mirrors that label. Conflating user speech
 * with model output is a §9 violation.
 *
 * Failure handling (rigor #3c): a transcription failure surfaces the hook's
 * error and persists NOTHING — the draft is never silently dropped or
 * mislabelled. A blank (silent) transcript is flagged, not invented.
 */

export interface VoiceToDraftProps {
  /** The section the spoken idea lands in as a user-authored block. */
  sectionId: string;
  deliverableId: string;
  /** The piece's backing research folder (the VOICE_CAPTURED event bucket). */
  investigationId: string;
  /** Index for the new block (append at the end of the section). */
  blockIndex: number;
  /** Refresh after the block is placed. */
  onDrafted: () => void | Promise<void>;
}

export default function VoiceToDraft({
  sectionId,
  deliverableId,
  investigationId,
  blockIndex,
  onDrafted,
}: VoiceToDraftProps) {
  const voice = useVoiceCapture();
  const [persisting, setPersisting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const capture = useCallback(async () => {
    setError(null);
    setSaved(false);
    if (voice.phase === "recording") {
      // Stop → transcribe → persist VOICE_CAPTURED (source_kind "user").
      const res = await voice.stopAndCapture({ investigationId });
      // rigor #3c: a transcription failure returns null + sets voice.error —
      // persist nothing, surface it, never a silent drop or a mislabel.
      if (!res) return;
      if (res.transcriptStatus === "empty" || !res.transcript.trim()) {
        setError("Didn't catch any words — try speaking again.");
        return;
      }
      setPersisting(true);
      try {
        // §9: the transcript is the writer's OWN speech → a user_authored
        // block (no node_id, no fabricated source). NEVER a model output.
        await placeBlock({
          section_id: sectionId,
          block_kind: "user_authored",
          provenance_kind: "user_authored",
          content: res.transcript.trim(),
          block_index: blockIndex,
          deliverable_id: deliverableId,
        });
        setSaved(true);
        // Living-TV: user-sourced voice draft saved — noted beat.
        emitWernerExperience("note_saved");
        await onDrafted();
      } catch (e) {
        emitWernerExperience("fail");
        setError(e instanceof Error ? e.message : "Couldn't save your spoken draft.");
      } finally {
        setPersisting(false);
      }
    } else {
      await voice.start();
    }
  }, [voice, investigationId, sectionId, deliverableId, blockIndex, onDrafted]);

  return (
    <div data-testid="voice-to-draft" className="flex items-center gap-2">
      <LemonButton
        variant="tertiary"
        size="sm"
        onClick={() => void capture()}
        disabled={persisting || voice.phase === "transcribing" || voice.phase === "persisting"}
      >
        {voice.phase === "recording"
          ? "■ Stop & add"
          : voice.phase === "transcribing"
            ? "Listening…"
            : persisting
              ? "Saving…"
              : "● Speak an idea"}
      </LemonButton>
      {saved && (
        <span className="text-[11px] text-aurora">Added — your spoken draft (user-sourced).</span>
      )}
      {voice.recorderState === "denied" && (
        <span className="text-[11px] text-sun-deep" role="alert">
          Microphone denied — you can still type.
        </span>
      )}
      {voice.error && (
        <span className="text-[11px] text-emperor" role="alert">
          {voice.error}
        </span>
      )}
      {error && (
        <span className="text-[11px] text-emperor" role="alert">
          {error}
        </span>
      )}
    </div>
  );
}
