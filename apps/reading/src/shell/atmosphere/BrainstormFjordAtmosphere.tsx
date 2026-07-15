import environment from "./brainstorm_fjord_idea_coast_v1.webp";
import { useState } from "react";

/** Decorative Brainstorm idea-coast; every working surface stays HTML. */
export function BrainstormFjordAtmosphere() {
  const [imageReady, setImageReady] = useState(false);
  return (
    <div
      aria-hidden="true"
      data-brainstorm-fjord-atmosphere=""
      data-brainstorm-fjord-image-ready={imageReady ? "true" : "false"}
      className="pointer-events-none absolute inset-0 overflow-hidden"
    >
      <img
        src={environment}
        alt=""
        draggable={false}
        decoding="async"
        onLoad={() => setImageReady(true)}
        className="absolute inset-0 h-full w-full object-cover object-center"
      />
    </div>
  );
}

export default BrainstormFjordAtmosphere;
