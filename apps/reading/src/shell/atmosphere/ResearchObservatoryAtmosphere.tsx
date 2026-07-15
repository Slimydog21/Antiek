import environment from "./research_observatory_environment_v1.webp";

/** Decorative Research-world atmosphere; every working surface stays HTML. */
export function ResearchObservatoryAtmosphere() {
  return (
    <div
      aria-hidden="true"
      data-research-observatory-atmosphere=""
      className="pointer-events-none absolute inset-0 overflow-hidden"
    >
      <img
        src={environment}
        alt=""
        draggable={false}
        decoding="async"
        className="absolute inset-0 h-full w-full object-cover object-[52%_center]"
      />
    </div>
  );
}

export default ResearchObservatoryAtmosphere;
