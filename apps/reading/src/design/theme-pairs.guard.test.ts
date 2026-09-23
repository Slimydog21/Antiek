/**
 * theme-pairs guard: no colour pair a component draws may read in one theme
 * and fail in the other.
 *
 * WHY: the semantic layer made surfaces follow the theme (bg-ice-1 is the
 * night card at night) while pigments stay put (text-ink is ink in both
 * themes, fill-ice-0 was meant to stay paper). A following colour paired with
 * a fixed one is legible in one theme and gone in the other: the outline
 * shelf's blocks drew ink on the night card at 1.13:1, and the brand mark on
 * the dock's Home key filled its lobes with the night card under ink folds,
 * also 1.13:1. Neither view has a story, so axe never saw them, and
 * tokens.contrast.test.ts checks what the tokens offer, not what call sites
 * pair. This guard reads the pairs call sites actually write.
 *
 * HOW: every JSX className in src (tests and stories aside) is resolved in
 * BOTH themes through the real tailwind.config.js and tokens.css (the parser
 * the other token gates use, tokenCss.ts): the text colour against the ground
 * beneath it (the element's own bg, else the nearest JSX ancestor's, with
 * /opacity washes composited over what lies under them), and an SVG stroke
 * against its own fill. A pair that clears its bar in one theme (AA 4.5:1 for
 * text, 3:1 for a drawn mark) and misses it in the other fails. Each pair is
 * checked at rest and in each interaction state the element paints itself
 * (hover:, focus:, focus-visible:, active:, with the cascade the browser
 * applies: at night `hover:text-ink` beats `dark:text-bright`). A className
 * that branches (`met ? "bg-shadow-2 hover:bg-shadow-1" : "bg-success"`, `on
 * && "…"`, cn() arguments) is checked branch by branch, and a `${prop}` span
 * reads the class strings this same file passes for that prop.
 *
 * WHAT IT SKIPS, on purpose: pairs that fail in BOTH themes (a bad pairing,
 * not a theme mismatch: axe owns those), an element whose ground differs by
 * branch of an ANCESTOR's className (undecidable here), a className past 32
 * branch combinations, class strings held in variables or passed from another
 * file, group-hover:/peer- states (another element's state), a ground painted
 * by an arbitrary value, aria-hidden decoration, and any ground a parent
 * COMPONENT paints: it follows JSX nesting, not renders, so FloatMenu's
 * panels, which sit on its ink island as separate components, are outside its
 * sight.
 *
 * PROOF IT BITES: point it at another tree and it reports that tree's pairs.
 *   TOKENS_CSS=<path> TAILWIND_CONFIG=<path> PAIRS_SRC=<dir> npx vitest run src/design/theme-pairs.guard.test.ts
 * At the merge base (2c35367ce, before the semantic layer) it reports 448
 * one-sided pairs (415 at rest, most of them dark:text-moonlight at 3.50 on
 * the night card; the rest in hover states). On the wave's first cut
 * (12fac9a10) it failed on four pairs: the shelf label (night 1.13), the
 * BrainMark folds (night 1.13), AccountMemory's error line (text-emperor on
 * bg-red-50, night 2.71) and FloatMenu's Hybrid note (text-sun-deep on the ink
 * island, day 3.09). At b0254d02c, when it read resting pairs only, it passed
 * while five hover pairs the wave broke went unseen: white on hover:bg-shadow-1
 * at night 2.54 ("Stop & upload", "Mark not met", and "Indeterminate" through
 * its accent prop), ChunkModal's link (hover:text-ink on hover:bg-ice-4, night
 * 1.32) and the AI log's undo (night 4.39).
 */
import { readdirSync, readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import resolveConfig from "tailwindcss/resolveConfig";
import ts from "typescript";
import { describe, expect, it } from "vitest";

import { contrastRatio, over, type Rgb } from "../../e2e/_ams/visible";
import { parseTokensCss, resolveTailwindColor, type Rgba, type ThemeName } from "./tokenCss";

const here = dirname(fileURLToPath(import.meta.url));
const APP = join(here, "..", "..");
const SRC = process.env.PAIRS_SRC ? resolve(process.env.PAIRS_SRC) : join(APP, "src");
const cssPath = process.env.TOKENS_CSS ? resolve(process.env.TOKENS_CSS) : join(here, "tokens.css");
const twPath = process.env.TAILWIND_CONFIG ? resolve(process.env.TAILWIND_CONFIG) : join(APP, "tailwind.config.js");

const sheet = parseTokensCss(readFileSync(cssPath, "utf8"));
const twModule = createRequire(import.meta.url)(twPath);
const theme = resolveConfig(twModule.default ?? twModule).theme as unknown as Record<string, Record<string, unknown>>;

type Kind = "text" | "bg" | "fill" | "stroke";
/** Flatten a resolved colour map to utility keys: {teal: {DEFAULT, 500}} → teal, teal-500. */
function flatten(obj: Record<string, unknown>, prefix = "", out = new Map<string, string>()): Map<string, string> {
  for (const [k, v] of Object.entries(obj ?? {})) {
    const key = k === "DEFAULT" ? prefix : prefix ? `${prefix}-${k}` : k;
    if (v && typeof v === "object") flatten(v as Record<string, unknown>, key, out);
    else if (typeof v === "string") out.set(key, v);
  }
  return out;
}
const COLORS: Record<Kind, Map<string, string>> = {
  text: flatten(theme.textColor),
  bg: flatten(theme.backgroundColor),
  fill: flatten(theme.fill),
  stroke: flatten(theme.stroke),
};

const THEMES: ThemeName[] = ["light", "dark"];
const BAR = { text: 4.5, mark: 3 } as const; // WCAG 1.4.3 / 1.4.11

/**
 * The interaction states a pair is checked in. Each is a pseudo-class on the
 * element itself, so `hover:bg-ice-4` (specificity 0,2,0) beats a resting
 * `dark:bg-charcoal-1`, which Tailwind emits as
 * `.dark\:bg-charcoal-1:where([data-theme="dark"], [data-theme="dark"] *)`
 * (0,1,0), and `dark:hover:bg-slate-1` (0,2,0, later in the sheet) beats both.
 * The same holds for text: at night `hover:text-ink` beats `dark:text-bright`.
 */
const STATES = ["hover", "focus", "focus-visible", "active"] as const;
type State = (typeof STATES)[number];
const isState = (v: string): v is State => (STATES as readonly string[]).includes(v);

type Tok = { kind: Kind; key: string; alpha: number; night: boolean; state: State | null };
/** A className's colour utilities: base, `dark:`, and the element's own interaction states. */
function colourTokens(classes: string[]): { toks: Tok[]; opaqueUnknownGround: boolean; unknownStates: Set<State> } {
  const toks: Tok[] = [];
  let opaqueUnknownGround = false;
  const unknownStates = new Set<State>();
  for (const raw of classes) {
    const parts = raw.split(":");
    const util = parts.pop()!;
    const variants = parts.filter((v) => !/^(sm|md|lg|xl|2xl)$/.test(v));
    const night = variants.includes("dark");
    const rest = variants.filter((v) => v !== "dark");
    if (rest.length > 1 || (rest.length === 1 && !isState(rest[0])) || variants.filter((v) => v === "dark").length > 1) continue;
    const state = (rest[0] as State | undefined) ?? null;
    const m = util.match(/^(text|bg|fill|stroke)-(.+?)(?:\/(\d+))?$/);
    if (!m) continue;
    const kind = m[1] as Kind;
    if (!COLORS[kind].has(m[2])) {
      // bg-[#123] / bg-[url()] / bg-gradient-to-r paint a ground this guard cannot read.
      if (kind === "bg" && /^(\[|gradient)/.test(m[2])) {
        if (state) unknownStates.add(state);
        else opaqueUnknownGround = true;
      }
      continue;
    }
    toks.push({ kind, key: m[2], alpha: m[3] ? Number(m[3]) / 100 : 1, night, state });
  }
  return { toks, opaqueUnknownGround, unknownStates };
}

/**
 * The tokens of `kind` in force for a theme and state, by the cascade above:
 * at night dark+state > state > dark > base; by day state > base.
 */
function inForce(toks: Tok[], kind: Kind, t: ThemeName, state: State | null = null): Tok[] {
  const tiers: Array<[boolean, State | null]> = [];
  if (t === "dark" && state) tiers.push([true, state]);
  if (state) tiers.push([false, state]);
  if (t === "dark") tiers.push([true, null]);
  tiers.push([false, null]);
  for (const [night, s] of tiers) {
    const hit = toks.filter((x) => x.kind === kind && x.night === night && x.state === s);
    if (hit.length) return hit;
  }
  return [];
}

function colour(t: ThemeName, tok: Tok): Rgba | null {
  const c = resolveTailwindColor(sheet, t, COLORS[tok.kind].get(tok.key)!);
  return c ? { ...c, a: c.a * tok.alpha } : null;
}
const name = (tok: Tok) =>
  `${tok.night ? "dark:" : ""}${tok.state ? `${tok.state}:` : ""}${tok.kind}-${tok.key}${tok.alpha < 1 ? `/${Math.round(tok.alpha * 100)}` : ""}`;
const onto = (top: Rgba, under: Rgb): Rgb => (top.a < 1 ? over(top, under) : top);

/**
 * The class lists a className={…} can resolve to: one per combination of its
 * branches (`on ? "x" : "y"`, `on && "z"`, a `${…}` span, cn()/clsx()
 * arguments). A `${prop}` span resolves to the class strings this file passes
 * for that prop (`<GradeButton accent="bg-shadow-2 hover:bg-shadow-1" />`).
 * Past MAX_ALTS combinations it falls back to one list holding every fragment,
 * which reads as an undecidable conditional and is skipped.
 */
const MAX_ALTS = 32;
type Alts = string[][];
const words = (text: string) => text.split(/\s+/).filter(Boolean);
const TOO_MANY = new Error("too many class branches");
const capped = (alts: Alts): Alts => {
  if (alts.length > MAX_ALTS) throw TOO_MANY;
  return alts;
};
const product = (a: Alts, b: Alts): Alts => capped(a.flatMap((x) => b.map((y) => [...x, ...y])));

/** Every string fragment under a node, as one list (the undecidable reading). */
function fragments(node: ts.Node): string[] {
  const out: string[] = [];
  const visit = (n: ts.Node) => {
    if (ts.isStringLiteral(n) || ts.isNoSubstitutionTemplateLiteral(n) || ts.isTemplateHead(n) || ts.isTemplateMiddle(n) || ts.isTemplateTail(n)) {
      out.push(...words(n.text));
    }
    n.forEachChild(visit);
  };
  visit(node);
  return out;
}

function alternatives(node: ts.Node, props: Map<string, string[]>): Alts {
  const all = (parts: ts.Node[]) => parts.reduce<Alts>((acc, p) => product(acc, alternatives(p, props)), [[]]);
  if (ts.isJsxExpression(node)) return node.expression ? alternatives(node.expression, props) : [[]];
  if (ts.isParenthesizedExpression(node) || ts.isAsExpression(node)) return alternatives(node.expression, props);
  if (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) return [words(node.text)];
  if (ts.isTemplateExpression(node)) {
    let acc: Alts = [words(node.head.text)];
    for (const span of node.templateSpans) acc = product(product(acc, alternatives(span.expression, props)), [words(span.literal.text)]);
    return acc;
  }
  if (ts.isConditionalExpression(node)) return capped([...alternatives(node.whenTrue, props), ...alternatives(node.whenFalse, props)]);
  if (ts.isBinaryExpression(node)) {
    const op = node.operatorToken.kind;
    if (op === ts.SyntaxKind.AmpersandAmpersandToken) return capped([[], ...alternatives(node.right, props)]);
    if (op === ts.SyntaxKind.BarBarToken || op === ts.SyntaxKind.QuestionQuestionToken) {
      return capped([...alternatives(node.left, props), ...alternatives(node.right, props)]);
    }
    if (op === ts.SyntaxKind.PlusToken) return product(alternatives(node.left, props), alternatives(node.right, props));
  }
  if (ts.isIdentifier(node)) return props.has(node.text) ? capped(props.get(node.text)!.map(words)) : [[]];
  if (ts.isArrayLiteralExpression(node)) return all([...node.elements]);
  if (ts.isCallExpression(node)) {
    // cn(a, b && "c"), clsx(…), [a, b].join(" "): every argument is a class source.
    const callee = ts.isPropertyAccessExpression(node.expression) ? [node.expression.expression] : [];
    return all([...callee, ...node.arguments]);
  }
  return [fragments(node)];
}

function classAlternatives(attr: ts.JsxAttribute, props: Map<string, string[]>): Alts {
  if (!attr.initializer) return [[]];
  try {
    return alternatives(attr.initializer, props);
  } catch (e) {
    if (e !== TOO_MANY) throw e;
    return [fragments(attr.initializer)];
  }
}

type Layer = { toks: Tok[]; unknown: boolean; unknownStates: Set<State> };
type Finding = { where: string; pair: string; theme: ThemeName; ratio: number; other: number };

/**
 * The opaque ground under the innermost layer, per theme: the nearest opaque
 * bg with every translucent wash above it composited on. `state` applies to
 * the innermost layer only (its own hover: fill). null = undecidable.
 */
function ground(stack: Layer[], t: ThemeName, state: State | null = null): { rgb: Rgb; label: string } | null {
  let i = stack.length - 1;
  const washes: Tok[] = [];
  if (state && stack[i]?.unknownStates.has(state)) return null;
  for (; i >= 0; i--) {
    if (stack[i].unknown) return null;
    const bgs = inForce(stack[i].toks, "bg", t, i === stack.length - 1 ? state : null);
    if (bgs.length > 1) return null;
    if (!bgs.length) continue;
    const c = colour(t, bgs[0]);
    if (!c) return null;
    washes.unshift(bgs[0]);
    if (c.a >= 1) break;
  }
  if (i < 0) return null; // no opaque ground in this file
  let rgb: Rgb = colour(t, washes[0])!;
  for (const w of washes.slice(1)) rgb = onto(colour(t, w)!, rgb);
  return { rgb, label: washes.map(name).join(" > ") };
}

/** The string-literal class props each component receives in this file: "GradeButton.accent" → [...]. */
function propStrings(sf: ts.SourceFile): Map<string, string[]> {
  const out = new Map<string, string[]>();
  const visit = (n: ts.Node) => {
    if ((ts.isJsxOpeningElement(n) || ts.isJsxSelfClosingElement(n)) && /^[A-Z]/.test(n.tagName.getText())) {
      for (const a of n.attributes.properties) {
        if (!ts.isJsxAttribute(a) || !a.initializer) continue;
        const lit = ts.isJsxExpression(a.initializer) ? a.initializer.expression : a.initializer;
        if (lit && (ts.isStringLiteral(lit) || ts.isNoSubstitutionTemplateLiteral(lit))) {
          const key = `${n.tagName.getText()}.${a.name.getText()}`;
          out.set(key, [...(out.get(key) ?? []), lit.text]);
        }
      }
    }
    n.forEachChild(visit);
  };
  visit(sf);
  return out;
}

/** The destructured props of the component enclosing `n`, resolved to what this file passes them. */
function enclosingProps(n: ts.Node, passed: Map<string, string[]>): Map<string, string[]> {
  const props = new Map<string, string[]>();
  for (let p: ts.Node | undefined = n.parent; p; p = p.parent) {
    if (!ts.isFunctionDeclaration(p) && !ts.isArrowFunction(p) && !ts.isFunctionExpression(p)) continue;
    const owner = ts.isFunctionDeclaration(p) ? p.name : ts.isVariableDeclaration(p.parent) ? p.parent.name : undefined;
    const param = p.parameters[0]?.name;
    if (owner && ts.isIdentifier(owner) && param && ts.isObjectBindingPattern(param)) {
      for (const el of param.elements) {
        if (!ts.isIdentifier(el.name)) continue;
        const prop = el.propertyName && ts.isIdentifier(el.propertyName) ? el.propertyName.text : el.name.text;
        const values = passed.get(`${owner.text}.${prop}`);
        if (values) props.set(el.name.text, values);
      }
    }
    return props;
  }
  return props;
}

/** The one-sided pairs in one TSX source. */
function scanSource(label: string, source: string): Finding[] {
  const findings: Finding[] = [];
  const seen = new Set<string>();
  const sf = ts.createSourceFile(label, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const passed = propStrings(sf);
  const where = (n: ts.Node) => `${label}:${sf.getLineAndCharacterOfPosition(n.getStart()).line + 1}`;
  const oneSided = (n: ts.Node, pair: (t: ThemeName) => { ratio: number; label: string } | null, bar: number) => {
    const r = THEMES.map(pair);
    if (!r[0] || !r[1]) return;
    const [lo, hi] = r[0].ratio <= r[1].ratio ? [0, 1] : [1, 0];
    const f = { where: where(n), pair: r[lo]!.label, theme: THEMES[lo], ratio: r[lo]!.ratio, other: r[hi]!.ratio };
    if (f.ratio < bar && f.other >= bar && !seen.has(`${f.where} ${f.pair}`)) {
      seen.add(`${f.where} ${f.pair}`);
      findings.push(f);
    }
  };
  const layerOf = (classes: string[], styled: boolean): Layer => {
    const { toks, opaqueUnknownGround, unknownStates } = colourTokens(classes);
    return { toks, unknown: opaqueUnknownGround || styled, unknownStates };
  };

  const visit = (n: ts.Node, stack: Layer[]) => {
    if (!ts.isJsxElement(n) && !ts.isJsxSelfClosingElement(n)) {
      n.forEachChild((c) => visit(c, stack));
      return;
    }
    const open = ts.isJsxElement(n) ? n.openingElement : n;
    const attrs = open.attributes.properties.filter(ts.isJsxAttribute);
    const attr = (a: string) => attrs.find((p) => p.name.getText() === a);
    const cls = attr("className");
    const alts = cls ? classAlternatives(cls, enclosingProps(n, passed)) : [[]];
    const styled = /background/i.test(attr("style")?.getText() ?? "");
    const hidden = /^aria-hidden(=\{?\s*(true|"true")\s*\}?)?$/.test(attr("aria-hidden")?.getText() ?? "");

    // Each branch the className can take is checked on its own, at rest and
    // in every interaction state it paints.
    for (const alt of alts) {
      const layer = layerOf(alt, styled);
      const { toks } = layer;
      const next = [...stack, layer];
      if (!hidden && toks.some((x) => x.kind === "text")) {
        const states = [null, ...STATES.filter((s) => toks.some((x) => x.state === s && (x.kind === "text" || x.kind === "bg")))];
        for (const state of states) {
          oneSided(n, (t) => {
            const fg = inForce(toks, "text", t, state);
            const g = ground(next, t, state);
            if (fg.length !== 1 || !g) return null;
            const c = colour(t, fg[0]);
            return c && { ratio: contrastRatio(onto(c, g.rgb), g.rgb), label: `${name(fg[0])} on ${g.label}` };
          }, BAR.text);
        }
      }
      if (toks.some((x) => x.kind === "stroke") && toks.some((x) => x.kind === "fill")) {
        oneSided(n, (t) => {
          const [s, f] = [inForce(toks, "stroke", t), inForce(toks, "fill", t)];
          if (s.length !== 1 || f.length !== 1) return null;
          const [sc, fc] = [colour(t, s[0]), colour(t, f[0])];
          return sc && fc && fc.a >= 1 ? { ratio: contrastRatio(onto(sc, fc), fc), label: `${name(s[0])} on ${name(f[0])}` } : null;
        }, BAR.mark);
      }
    }
    // Children see every branch at once: a ground that differs by branch is undecidable for them.
    const next = [...stack, layerOf(alts.flat(), styled)];
    if (ts.isJsxElement(n)) n.children.forEach((c) => visit(c, next));
    else n.forEachChild((c) => visit(c, next));
  };
  visit(sf, []);
  return findings;
}

function scan(): Finding[] {
  const files: string[] = [];
  (function walk(dir: string) {
    for (const e of readdirSync(dir, { withFileTypes: true })) {
      const p = join(dir, e.name);
      if (e.isDirectory()) walk(p);
      else if (e.name.endsWith(".tsx") && !/\.(test|stories)\.tsx$/.test(e.name)) files.push(p);
    }
  })(SRC);
  return files.flatMap((f) => scanSource(relative(SRC, f), readFileSync(f, "utf8")));
}

/**
 * Pairs that already failed AA on origin/main before the semantic layer
 * (2c35367ce, resolved through that tree's config and tokens; the ratio there
 * is in brackets, night unless marked). The semantic layer raised some of them
 * but not past 4.5 while their other side passes, so they read as one-sided
 * now. They are moonlight on a sun-tinted wash, ink on a sun wash at night,
 * and hover:text-ink overriding dark:text-bright on the night card: the views
 * own them, not the tokens. This set only shrinks. Keyed by file and pair, not
 * by line, so edits nearby do not churn it.
 */
const PRE_EXISTING = new Set([
  "components/ChatInput.tsx | dark:text-moonlight on dark:bg-slate-1", // [3.05] now 4.35
  "components/ModelPicker.tsx | dark:text-moonlight on dark:bg-charcoal-1 > dark:bg-sun/10", // [3.08] now 4.39
  "components/ModelPicker.tsx | dark:text-moonlight on dark:bg-charcoal-1 > dark:bg-sun/10 > bg-moonlight/15", // [2.63] now 3.54
  "modes/Multimedia/index.tsx | text-ink on dark:bg-charcoal-2 > bg-sun/10", // [1.44] now 1.44
  "modes/Notebook/SlashMenu.tsx | dark:text-moonlight on dark:bg-charcoal-2 > dark:bg-sun/15", // [2.39] now 3.41
  "modes/Reading/PersonalSpace/index.tsx | dark:text-moonlight on dark:bg-charcoal-2 > bg-sun/10", // [2.75] now 3.92
  // interaction states
  "components/AdSlot/AdSlot.tsx | hover:text-ink on dark:bg-charcoal-2", // [1.13] now 1.13
  "components/ChatInput.tsx | dark:text-moonlight on hover:bg-shadow-2", // [2.02] now 2.87
  "modes/InvestigationsIndex/index.tsx | hover:text-ink on dark:bg-charcoal-2", // [1.13] now 1.13
  "modes/ResearchWorkstation/CascadeProposal.tsx | hover:text-sun on bg-ice-0", // [day 1.36] now day 1.35
  "modes/ResearchWorkstation/TrajectoryView.tsx | hover:text-ink on dark:bg-charcoal-2", // [1.13] now 1.13
  "modes/SkillRuleDetail/index.tsx | hover:text-ink on dark:bg-charcoal-2", // [1.13] now 1.13
]);
const keyOf = (f: Finding) => `${f.where.replace(/:\d+$/, "")} | ${f.pair}`;

describe("theme-pairs guard", () => {
  const findings = scan();

  it("no pair a call site draws reads in one theme and fails in the other", () => {
    const fresh = findings
      .filter((f) => !PRE_EXISTING.has(keyOf(f)))
      .map((f) => `${f.where}  ${f.pair}: ${f.theme} ${f.ratio.toFixed(2)} (other theme ${f.other.toFixed(2)})`);
    expect(fresh).toEqual([]);
  });

  it("the pre-existing list only shrinks: every entry still occurs", () => {
    const seen = new Set(findings.map(keyOf));
    expect([...PRE_EXISTING].filter((k) => !seen.has(k))).toEqual([]);
  });

  it("bites: a fixed pigment on a following ground is caught, a dark: pair or a fixed ground clears it", () => {
    const one = (jsx: string) => scanSource("fixture.tsx", `export const F = () => (${jsx});`);
    // ink on the card that turns night (the outline-shelf defect)
    expect(one(`<li className="bg-ice-1"><p className="text-ink">label</p></li>`)).toMatchObject([
      { pair: "text-ink on bg-ice-1", theme: "dark" },
    ]);
    // paper lobes under ink folds, drawn from a key that follows the card (the BrainMark defect)
    expect(one(`<svg><path className="fill-card stroke-ink" /></svg>`)).toMatchObject([
      { pair: "stroke-ink on fill-card", theme: "dark" },
    ]);
    // the fixes: pair the text for night, or keep ink on a ground that does not flip
    expect(one(`<li className="bg-ice-1"><p className="text-ink dark:text-bright">label</p></li>`)).toEqual([]);
    expect(one(`<li className="bg-sun"><p className="text-ink">label</p></li>`)).toEqual([]);
    // what it cannot decide it skips: a conditional ground, decoration
    expect(one(`<li className={on ? "bg-sun" : "bg-ice-1"}><p className="text-ink">label</p></li>`)).toEqual([]);
    expect(one(`<li className="bg-ice-1"><span aria-hidden="true" className="text-ink">x</span></li>`)).toEqual([]);
  });

  it("bites in interaction states, branch by branch, and through a class prop", () => {
    const one = (jsx: string) => scanSource("fixture.tsx", `export const F = () => (${jsx});`);
    // at night hover:text-ink beats dark:text-bright, over a hover fill that follows the theme (ChunkModal's link)
    expect(one(`<a className="text-ink dark:text-bright bg-ice-3 dark:bg-charcoal-1 hover:text-ink hover:bg-ice-4">x</a>`)).toMatchObject([
      { pair: "hover:text-ink on hover:bg-ice-4", theme: "dark" },
    ]);
    // dropping the hover text, or giving it a night value, clears it
    expect(one(`<a className="text-ink dark:text-bright bg-ice-3 dark:bg-charcoal-1 hover:bg-ice-4">x</a>`)).toEqual([]);
    expect(one(`<a className="text-ink dark:text-bright bg-ice-3 hover:text-ink dark:hover:text-bright hover:bg-ice-4">x</a>`)).toEqual([]);
    // one branch of a conditional: white text hovering onto a fill that turns paper by day
    expect(one(`<button className={met ? "bg-ink text-white hover:bg-ice-4" : "bg-success text-white dark:text-ink"}>x</button>`)).toMatchObject([
      { pair: "text-white on hover:bg-ice-4", theme: "light" },
    ]);
    // the class arrives through a prop this file passes (Outcomes' GradeButton accent)
    const viaProp = scanSource(
      "fixture.tsx",
      `function Grade({ accent }: { accent: string }) { return <button className={\`text-ice-0 \${accent}\`}>x</button>; }
       export const F = () => <Grade accent="bg-ink hover:bg-ice-4" />;`,
    );
    expect(viaProp).toMatchObject([{ where: "fixture.tsx:1", pair: "text-ice-0 on hover:bg-ice-4", theme: "light" }]);
    // the ink button and its slate hover hold in both themes (the bg-shadow-1 fill is a fixed pigment)
    expect(one(`<button className="bg-shadow-2 text-white hover:bg-shadow-1">x</button>`)).toEqual([]);
  });
});
