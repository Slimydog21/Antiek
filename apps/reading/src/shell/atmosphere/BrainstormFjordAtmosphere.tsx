import environment from "./brainstorm_fjord_idea_coast_v1.webp";

/** Decorative Brainstorm idea-coast; every working surface stays HTML. */
export function BrainstormFjordAtmosphere() {
  return (
    <div
      aria-hidden="true"
      data-brainstorm-fjord-atmosphere=""
      className="pointer-events-none absolute inset-0 overflow-hidden"
    >
      <img
        src={environment}
        alt=""
        draggable={false}
        decoding="async"
        className="absolute inset-0 h-full w-full object-cover object-center"
      />
    </div>
  );
}

export default BrainstormFjordAtmosphere;
