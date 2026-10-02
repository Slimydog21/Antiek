/** Fixed-width UTF-16 units preserve every opaque ID, including lone surrogates. */
export function panelFocusId(id: string): string {
  let encoded = "";
  for (let i = 0; i < id.length; i += 1) encoded += id.charCodeAt(i).toString(16).padStart(4, "0");
  return `panel-title-${encoded}`;
}
