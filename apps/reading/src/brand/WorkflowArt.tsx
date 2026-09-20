/**
 * WorkflowArt — the mascot, doing the thing each product is for.
 *
 * Research / Read / Write / Speak each get the same character performing that
 * workflow's verb: a magnifier, an open book, a pencil, a microphone. One
 * character, four jobs — so the set reads as a family rather than four
 * unrelated icons, and a new door only needs a new prop rather than a new
 * illustration language.
 *
 * Generated from the brand LoRA (antiek-brain-doodle-v1) at one shared scale,
 * so the four sit at matching optical weight beside each other.
 *
 * Decorative only: every surface that renders this already names the workflow
 * in adjacent text, so the image is aria-hidden and carries an empty alt. It
 * must never be the only thing announcing which product you are looking at.
 *
 * Sizing: these are photographic-detail marks, not glyphs. Below ~48px the
 * prop (magnifier, book, pencil, mic) stops resolving and all four collapse
 * toward the same coral blob — measured on the size ladder. Do not use this in
 * the rail (24–28px); the rail keeps its geometric glyphs.
 */
import type { Workflow } from "../shell/workflowTaxonomy";


import biographyArt from "./workflow-art/biography-512.png";
import readArt from "./workflow-art/read-512.png";
import researchArt from "./workflow-art/research-512.png";
import speakArt from "./workflow-art/speak-512.png";
import writeArt from "./workflow-art/write-512.png";

/** Features that carry their own art. The four product doors, plus surfaces
 *  that compose several doors and so cannot borrow one door's prop —
 *  Biography draws on research, writing and gathered voices at once. */
export type ArtFeature = Exclude<Workflow, "shared"> | "biography";

const ART: Partial<Record<ArtFeature, string>> = {
  research: researchArt,
  read: readArt,
  write: writeArt,
  speak: speakArt,
  biography: biographyArt,
};

/** The floor at which all four props still resolve as distinct objects. */
export const WORKFLOW_ART_MIN_PX = 48;

type Props = {
  /** Which feature's art to draw. `shared`/undefined renders nothing. */
  workflow: ArtFeature | Workflow | undefined;
  /** Rendered edge length in px. Values below the floor are clamped, not honoured. */
  size?: number;
  className?: string;
};

export default function WorkflowArt({ workflow, size = 64, className }: Props) {
  const src = workflow ? ART[workflow as ArtFeature] : undefined;
  if (!src) return null;
  const px = Math.max(size, WORKFLOW_ART_MIN_PX);
  return (
    <img
      src={src}
      alt=""
      aria-hidden="true"
      data-workflow-art={workflow}
      width={px}
      height={px}
      className={className}
      style={{ display: "block", width: px, height: px, objectFit: "contain" }}
    />
  );
}
