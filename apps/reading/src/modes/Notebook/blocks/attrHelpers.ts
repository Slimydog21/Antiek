/**
 * Helpers for declaring TipTap node attributes with explicit
 * parseHTML / renderHTML behavior.
 *
 * TipTap picks up many attributes by default but the behavior isn't
 * documented as stable across versions + relies on the parser
 * inferring kebab-vs-camel naming heuristics. Being explicit
 * guarantees AI-tool-call-dispatched HTML round-trips losslessly
 * through parse → render → re-parse:
 *
 *   addAttributes() {
 *     return {
 *       text:        stringAttr("text"),
 *       page:        intAttr("page"),
 *       document_id: stringAttr("document_id"),
 *     };
 *   }
 */

type AttrRecord = Record<string, unknown>;

/** String attribute. Null when absent. */
export function stringAttr(name: string) {
  return {
    default: null as string | null,
    parseHTML: (el: HTMLElement) => el.getAttribute(name),
    renderHTML: (attrs: AttrRecord) =>
      attrs[name] != null ? { [name]: String(attrs[name]) } : {},
  };
}

/** Integer attribute. Null when absent or malformed. */
export function intAttr(name: string) {
  return {
    default: null as number | null,
    parseHTML: (el: HTMLElement) => {
      const v = el.getAttribute(name);
      if (v == null || v === "") return null;
      const n = parseInt(v, 10);
      return Number.isFinite(n) ? n : null;
    },
    renderHTML: (attrs: AttrRecord) =>
      attrs[name] != null ? { [name]: String(attrs[name]) } : {},
  };
}
