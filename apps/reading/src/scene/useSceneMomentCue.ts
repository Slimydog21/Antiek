import { useEffect, useRef } from "react";

import type { SceneMood } from "./mood";
import { momentForTransition, type WernerMomentId } from "../brand/wernerMoments";

export type LiveSceneMoment = Extract<WernerMomentId, "daybreak" | "dusk-settle">;

export interface SceneMomentCue {
  sequence: number;
  moment: LiveSceneMoment;
}

/**
 * Transports authored presentation moments from the one committed scene mood
 * boundary. It owns no clock, theme, media query, mascot state, or replay.
 */
export function useSceneMomentCue(
  mood: SceneMood,
  onTransition?: (cue: SceneMomentCue) => void,
): void {
  const previousRef = useRef<SceneMood | null>(null);
  const sequenceRef = useRef(0);

  useEffect(() => {
    const moment = momentForTransition(previousRef.current, mood);
    if (moment?.id === "daybreak" || moment?.id === "dusk-settle") {
      sequenceRef.current += 1;
      onTransition?.({ sequence: sequenceRef.current, moment: moment.id });
    }
    previousRef.current = mood;
  }, [mood, onTransition]);
}
