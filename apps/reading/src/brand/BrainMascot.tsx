/**
 * BrainMascot.tsx — canonical Antiek brain mark (the U-02 slot, brain edition).
 *
 * The same four-slot contract Werner held — idle / thinking / empty / celebrate,
 * enforced by the dev runtime guard below — rendered from the operator's
 * Krea-generated brain mascot set (tools/brand/mascot-brain/). Mission tie-in:
 * Antiek uses AI to amplify the human brain, never replace it; the mascot *is*
 * the thesis, so the mark is a brain, not a penguin.
 *
 * Beyond the still pose map, the brain is ALIVE (the operator's animation brief):
 *   - blink        — idle only; crossfades to a closed-eyes frame every ~3–6 s
 *                    (closed-eyes variant generated from the same anchor via
 *                    Krea i2i, rembg-cut; provenance in PROFILE.md §3).
 *   - breathing    — gentle 1.015 sway on idle (CSS keyframes, `brain-idle`).
 *   - pointer tilt — the character leans toward the cursor (±4–5°, springed
 *                    via framer-motion) so it always appears to be watching.
 *   - hover wave   — a quick rotate wobble + scale bump on pointer hover.
 *
 * Restraint is load-bearing exactly as it was for Werner: the mark appears in
 * rail (idle), AI working (thinking), blank states (empty), and core-action
 * complete (celebrate). Nowhere else. Motion is CSS + two motion values and
 * collapses under prefers-reduced-motion (media query + useReducedMotion).
 *
 * The floating project-home station (shell/PenguinMascot.tsx) is intentionally
 * NOT re-skinned here — its fishing-rig interaction model is a ratified
 * operator decision and is tracked separately.
 */
import { useEffect, useState } from "react";
import { motion, useMotionValue, useReducedMotion, useSpring } from "framer-motion";
import type { CSSProperties } from "react";

import type { WernerMood } from "../design/tokens";
import type { SceneMood } from "../scene/mood";
import { wernerMoodForScene } from "./wernerSceneMap";

import brainIdle from "./mascot-brain/01_hero_front_transparent.png";
import brainClosed from "./mascot-brain/blink_closed_transparent.png";
import brainThinking from "./mascot-brain/mood_thinking.png";
import brainEmpty from "./mascot-brain/mood_sleepy.png";
import brainCelebrate from "./mascot-brain/mood_excited.png";

import "./mascot-brain/brainMascot.css";

const MOODS = ["idle", "thinking", "empty", "celebrate"] as const;

// Mood → Krea pose. Idle is the cute default; thinking, empty (sleepy) and
// celebrate (excited) carry the same character into the other three slots.
const POSE: Record<(typeof MOODS)[number], string> = {
  idle: brainIdle,
  thinking: brainThinking,
  empty: brainEmpty,
  celebrate: brainCelebrate,
};

type Props = {
  mood?: WernerMood;
  scene?: SceneMood;
  size?: number;
  label?: string;
  className?: string;
  // Positioning passthrough — animated wrappers place the mark absolutely;
  // merged after the intrinsic size box.
  style?: CSSProperties;
};

// Blink rhythm — irregular on purpose; a fixed 4 s blink reads robotic.
const BLINK_MIN_MS = 3200;
const BLINK_MAX_MS = 5800;
const BLINK_CLOSED_MS = 150;

export default function BrainMascot({
  mood,
  scene,
  size = 28,
  label,
  className,
  style,
}: Props) {
  const effectiveMood = mood ?? (scene ? wernerMoodForScene(scene) : "idle");
  const reduceMotion = (useReducedMotion() ?? false) === true;

  // Dev runtime guard — the mechanical half of U-02, same as Werner's.
  if (
    process.env.NODE_ENV !== "production" &&
    effectiveMood &&
    !(MOODS as readonly string[]).includes(effectiveMood)
  ) {
    throw new Error(
      `BrainMascot: invalid mood "${effectiveMood}". Only ${MOODS.join(", ")} are permitted. ` +
        "The four-slot restraint is non-negotiable per brand/README.md and U-02."
    );
  }

  const resolvedMood = effectiveMood as (typeof MOODS)[number];
  const [blinking, setBlinking] = useState(false);
  const [hovered, setHovered] = useState(false);

  // Blink scheduler — idle only, skipped entirely under reduced motion.
  useEffect(() => {
    if (reduceMotion || resolvedMood !== "idle") return;
    let next: number | undefined;
    let close: number | undefined;
    const schedule = () => {
      const delay = BLINK_MIN_MS + Math.random() * (BLINK_MAX_MS - BLINK_MIN_MS);
      next = window.setTimeout(() => {
        setBlinking(true);
        close = window.setTimeout(() => setBlinking(false), BLINK_CLOSED_MS);
        schedule();
      }, delay);
    };
    schedule();
    return () => {
      if (next !== undefined) window.clearTimeout(next);
      if (close !== undefined) window.clearTimeout(close);
    };
  }, [reduceMotion, resolvedMood]);

  // Pointer tilt — the brain leans toward the cursor. Springs make it feel
  // weighted rather than jittery; the listener is passive and viewport-wide.
  const tiltX = useMotionValue(0);
  const tiltY = useMotionValue(0);
  const springX = useSpring(tiltX, { stiffness: 140, damping: 18 });
  const springY = useSpring(tiltY, { stiffness: 140, damping: 18 });
  useEffect(() => {
    if (reduceMotion) return;
    const onMove = (e: PointerEvent) => {
      const nx = (e.clientX / window.innerWidth) * 2 - 1;
      const ny = (e.clientY / window.innerHeight) * 2 - 1;
      tiltY.set(nx * 5);
      tiltX.set(-ny * 4);
    };
    window.addEventListener("pointermove", onMove, { passive: true });
    return () => window.removeEventListener("pointermove", onMove);
  }, [reduceMotion, tiltX, tiltY]);

  const rootClass = resolvedMood === "idle" ? "brain-idle" : "";

  return (
    <span
      role="img"
      aria-label={label || `Antiek ${resolvedMood}`}
      className={`inline-block align-middle ${rootClass} ${className ?? ""}`}
      style={{ width: size, height: size, position: "relative", perspective: "600px", ...style }}
      onPointerEnter={() => setHovered(true)}
      onPointerLeave={() => setHovered(false)}
    >
      <motion.span
        className="brain-tilt"
        style={{
          display: "block",
          width: "100%",
          height: "100%",
          rotateX: springX,
          rotateY: springY,
          transformStyle: "preserve-3d",
        }}
        whileHover={
          reduceMotion
            ? undefined
            : { scale: 1.06, rotate: [0, -3, 3, 0], transition: { duration: 0.5 } }
        }
      >
        <img
          src={POSE[resolvedMood]}
          alt=""
          aria-hidden="true"
          draggable={false}
          className="brain-pose"
          style={{ display: "block", width: "100%", height: "100%", objectFit: "contain" }}
        />
        {resolvedMood === "idle" && (
          <img
            src={brainClosed}
            alt=""
            aria-hidden="true"
            draggable={false}
            className={`brain-blink ${blinking || hovered ? "brain-blink-on" : ""}`}
            style={{ display: "block", width: "100%", height: "100%", objectFit: "contain" }}
          />
        )}
      </motion.span>
    </span>
  );
}
