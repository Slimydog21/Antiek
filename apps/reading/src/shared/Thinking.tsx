import WernerThinking from "../brand/werner/animated/WernerThinking";

/**
 * Thinking — the one "the AI is working" beat every door shares.
 *
 * Wraps U-02's Werner thinking mood (the idle penguin + the four aurora
 * thought-dots) so the same signal reads as "working" in Research, Read,
 * Write, and Speak — instead of the AI being felt in one door and invisible
 * in the other three. An optional `status` line carries plain-language
 * progress ("reading sources…", "drafting…").
 *
 * Plain language ONLY: the status is a human sentence, never a raw phase or
 * substrate name (those translate at the UI edge via the M4 glossary before
 * they reach here). Reduced-motion safety is inherited from Werner /
 * animations.css — this component adds no motion of its own.
 */
type Props = {
  /** Plain-language progress, e.g. "reading sources…". Omit for the bare beat. */
  status?: string;
  /** Werner mark size in px (24 / 40 / 64 target sizes). Default 40. */
  size?: number;
  /**
   * Accessible label for the live indicator — the screen-reader sentence
   * for the state. Defaults to a plain "The AI is working".
   */
  label?: string;
  className?: string;
};

export default function Thinking({
  status,
  size = 40,
  label = "The AI is working",
  className,
}: Props) {
  return (
    <span
      className={
        className
          ? `inline-flex items-center gap-2 ${className}`
          : "inline-flex items-center gap-2"
      }
    >
      <WernerThinking size={size} label={label} />
      {status ? (
        <span className="text-xs font-mono text-ink-mute dark:text-moonlight">
          {status}
        </span>
      ) : null}
    </span>
  );
}
