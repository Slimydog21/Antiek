/**
 * tokenCss.ts — read src/design/tokens.css the way the browser does, for the
 * token gates (token-parity.test.ts, tokens.contrast.test.ts,
 * scripts/check_token_parity.ts). Not imported by app code.
 *
 * It parses the sheet into its cascade layers (top-level :root blocks, the
 * [data-theme="dark"] night block, the no-JS @media fallback), resolves var()
 * chains per theme, and resolves a Tailwind colour value
 * (`rgb(var(--x-rgb) / <alpha-value>)`, `var(--x)`, or a literal) to the
 * colour that actually renders. Gates computed from this can see what
 * components consume, not just what a token file claims.
 */
export type ThemeName = "light" | "dark";
export type Rgba = { r: number; g: number; b: number; a: number };

export interface TokenSheet {
  /** Every top-level `:root { … }` declaration, in source order. */
  root: Map<string, string>;
  /** The night block: `:root[data-theme="dark"]`, else the dark @media :root block. */
  night: Map<string, string>;
  /** Declarations inside `@media (prefers-color-scheme: dark)`, if any. */
  fallback: Map<string, string>;
  /** Raw declaration lists (name: value) per block, in order, for identity checks. */
  nightList: string[];
  fallbackList: string[];
}

function stripComments(src: string): string {
  return src.replace(/\/\*[\s\S]*?\*\//g, "");
}

/** Split `a { b } c { d }` (one nesting level of @media allowed) into [selector, body]. */
function blocks(src: string): Array<{ selector: string; body: string }> {
  const out: Array<{ selector: string; body: string }> = [];
  let i = 0;
  while (i < src.length) {
    const open = src.indexOf("{", i);
    if (open === -1) break;
    const selector = src.slice(i, open).trim();
    let depth = 1;
    let j = open + 1;
    while (j < src.length && depth > 0) {
      if (src[j] === "{") depth++;
      else if (src[j] === "}") depth--;
      j++;
    }
    out.push({ selector, body: src.slice(open + 1, j - 1) });
    i = j;
  }
  return out;
}

function declarations(body: string): Array<[string, string]> {
  const out: Array<[string, string]> = [];
  for (const m of body.matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)) out.push([m[1], m[2].trim()]);
  return out;
}

export function parseTokensCss(css: string): TokenSheet {
  const root = new Map<string, string>();
  const night = new Map<string, string>();
  const fallback = new Map<string, string>();
  const nightList: string[] = [];
  const fallbackList: string[] = [];
  let explicitNight = false;
  for (const { selector, body } of blocks(stripComments(css))) {
    const sel = selector.replace(/\s+/g, " ");
    if (sel === ":root") {
      for (const [k, v] of declarations(body)) root.set(k, v);
    } else if (/^:root\[data-theme="dark"\]$/.test(sel)) {
      explicitNight = true;
      for (const [k, v] of declarations(body)) {
        night.set(k, v);
        nightList.push(`${k}: ${v}`);
      }
    } else if (/^@media \(prefers-color-scheme: ?dark\)$/.test(sel)) {
      for (const inner of blocks(body)) {
        for (const [k, v] of declarations(inner.body)) {
          fallback.set(k, v);
          fallbackList.push(`${k}: ${v}`);
        }
      }
    }
  }
  if (!explicitNight) {
    // Pre-data-theme sheets carried night only in the media block.
    for (const [k, v] of fallback) night.set(k, v);
  }
  return { root, night, fallback, nightList, fallbackList };
}

/** The specified value of `--name` in a theme, with every var() substituted. */
export function resolveVar(sheet: TokenSheet, theme: ThemeName, name: string, depth = 0): string | null {
  if (depth > 20) throw new Error(`var() cycle at ${name}`);
  const raw = (theme === "dark" ? sheet.night.get(name) : undefined) ?? sheet.root.get(name);
  if (raw === undefined) return null;
  let unresolved = false;
  const value = raw.replace(/var\((--[\w-]+)\)/g, (_, ref: string) => {
    const v = resolveVar(sheet, theme, ref, depth + 1);
    if (v === null) unresolved = true;
    return v ?? "";
  });
  return unresolved ? null : value;
}

/** Parse `#rgb[a]`, `#rrggbb[aa]`, `r g b` channel triplets, and rgb()/rgba(). */
export function toRgba(value: string): Rgba | null {
  const v = value.trim();
  const hex = v.match(/^#([0-9a-f]{3,8})$/i);
  if (hex) {
    let h = hex[1];
    if (h.length <= 4) h = [...h].map((c) => c + c).join("");
    return {
      r: parseInt(h.slice(0, 2), 16),
      g: parseInt(h.slice(2, 4), 16),
      b: parseInt(h.slice(4, 6), 16),
      a: h.length === 8 ? parseInt(h.slice(6, 8), 16) / 255 : 1,
    };
  }
  const fn = v.match(/^rgba?\(([^)]+)\)$/i);
  const parts = (fn ? fn[1] : v).split(/[\s,/]+/).filter(Boolean);
  if ((fn || /^\d+ \d+ \d+$/.test(v)) && parts.length >= 3) {
    const [r, g, b] = parts.slice(0, 3).map(Number);
    const a = parts[3] === undefined ? 1 : Number(parts[3].replace("%", "")) / (parts[3].endsWith("%") ? 100 : 1);
    if ([r, g, b, a].every((n) => Number.isFinite(n))) return { r, g, b, a };
  }
  return null;
}

/** The colour a Tailwind colour value renders to in a theme (alpha 1). */
export function resolveTailwindColor(sheet: TokenSheet, theme: ThemeName, twValue: string): Rgba | null {
  const channel = twValue.match(/^rgb\(var\((--[\w-]+)\) \/ <alpha-value>\)$/);
  if (channel) {
    const triplet = resolveVar(sheet, theme, channel[1]);
    return triplet === null ? null : toRgba(triplet);
  }
  const plain = twValue.match(/^var\((--[\w-]+)\)$/);
  if (plain) {
    const v = resolveVar(sheet, theme, plain[1]);
    return v === null ? null : toRgba(v);
  }
  return toRgba(twValue);
}
