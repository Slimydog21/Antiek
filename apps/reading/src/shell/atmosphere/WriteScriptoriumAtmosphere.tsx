import environment from "./write_scriptorium_environment_v1.webp";

/** Decorative Write-world atmosphere; the editor and every control stay HTML. */
export function WriteScriptoriumAtmosphere() {
  return (
    <div
      aria-hidden="true"
      data-write-scriptorium-atmosphere=""
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

export default WriteScriptoriumAtmosphere;
