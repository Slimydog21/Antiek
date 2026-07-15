import environment from "./read_glacial_cloister_environment_v1.webp";

/** Decorative Read-world atmosphere; books, pages, annotations, and state stay HTML. */
export function ReadGlacialCloisterAtmosphere() {
  return (
    <div aria-hidden="true" data-read-glacial-cloister-atmosphere="" className="pointer-events-none absolute inset-0 overflow-hidden">
      <img src={environment} alt="" draggable={false} decoding="async" className="absolute inset-0 h-full w-full object-cover object-center" />
    </div>
  );
}

export default ReadGlacialCloisterAtmosphere;
