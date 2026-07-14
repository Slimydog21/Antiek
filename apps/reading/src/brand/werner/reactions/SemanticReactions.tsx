import type { CSSProperties, ReactNode } from "react";

import Werner, { type WernerMood } from "../../Werner";
import "./semantic-reactions.css";

type SemanticReactionKind = "curious" | "happy" | "dizzy" | "hit";

const DURATION_MS: Record<SemanticReactionKind, number> = {
  curious: 1200,
  happy: 800,
  dizzy: 1300,
  hit: 800,
};

const MOOD: Record<SemanticReactionKind, WernerMood> = {
  curious: "thinking",
  happy: "idle",
  dizzy: "empty",
  hit: "idle",
};

const LABEL: Record<SemanticReactionKind, string> = {
  curious: "Werner examines the evidence",
  happy: "Werner marks the work verified",
  dizzy: "Werner regains his bearings",
  hit: "Werner bumps the control",
};

type Props = { size: number; reduced: boolean };

function EvidenceCard() {
  return (
    <svg
      className="werner-semantic__evidence"
      viewBox="0 0 24 30"
      aria-hidden="true"
    >
      <rect x="2" y="3" width="20" height="25" rx="1" />
      <path d="M7 9h10M7 14h8M7 19h10" />
      <path className="werner-semantic__spark" d="M18 1v4M16 3h4" />
    </svg>
  );
}

function VerificationStamp() {
  return (
    <svg
      className="werner-semantic__stamp"
      viewBox="0 0 30 30"
      aria-hidden="true"
    >
      <circle cx="15" cy="15" r="12" />
      <circle cx="15" cy="15" r="8" />
      <path d="m10 15 3 3 7-7" />
    </svg>
  );
}

function PaperclipOrbit() {
  return (
    <svg
      className="werner-semantic__orbit"
      viewBox="0 0 64 28"
      aria-hidden="true"
    >
      <g className="werner-semantic__paperclips">
        <path d="M8 17c-5-1-5-8 0-9h8c5 1 5 8 0 9H9c-2 0-2-3 0-3h7" />
        <path d="M28 7c-1-5 6-7 8-2l2 7c1 5-6 7-8 2l-2-6c-1-2 2-3 3-1l2 6" />
        <path d="M48 18c-4-3 0-9 4-7l7 4c4 3 0 9-4 7l-6-3c-2-1 0-4 2-2l5 3" />
      </g>
    </svg>
  );
}

function BrassTab() {
  return (
    <svg
      className="werner-semantic__tab"
      viewBox="0 0 22 38"
      aria-hidden="true"
    >
      <path d="M2 3h18v32H8l-6-6Z" />
      <circle cx="11" cy="10" r="3" />
    </svg>
  );
}

const CHROME: Record<SemanticReactionKind, ReactNode> = {
  curious: <EvidenceCard />,
  happy: <VerificationStamp />,
  dizzy: <PaperclipOrbit />,
  hit: <BrassTab />,
};

function SemanticReaction({
  kind,
  size,
  reduced,
}: Props & { kind: SemanticReactionKind }) {
  const style = {
    width: size,
    height: size,
    "--werner-semantic-duration": `${DURATION_MS[kind]}ms`,
  } as CSSProperties;

  return (
    <span
      role="img"
      aria-label={LABEL[kind]}
      className={`werner-semantic werner-semantic--${kind}`}
      data-werner-reaction={kind}
      data-duration-ms={DURATION_MS[kind]}
      data-reduced={reduced ? "true" : "false"}
      style={style}
    >
      <span className="werner-semantic__mark" aria-hidden="true">
        <Werner mood={MOOD[kind]} size={size} />
      </span>
      {CHROME[kind]}
    </span>
  );
}

export function WernerCurious(props: Props) {
  return <SemanticReaction kind="curious" {...props} />;
}

export function WernerHappy(props: Props) {
  return <SemanticReaction kind="happy" {...props} />;
}

export function WernerDizzy(props: Props) {
  return <SemanticReaction kind="dizzy" {...props} />;
}

export function WernerHit(props: Props) {
  return <SemanticReaction kind="hit" {...props} />;
}

export { DURATION_MS as WERNER_SEMANTIC_DURATION_MS };
