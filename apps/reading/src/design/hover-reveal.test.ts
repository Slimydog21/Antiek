/**
 * Hover-revealed controls must show on touch screens and to the keyboard.
 *
 * tailwind.config.js sets future.hoverOnlyWhenSupported, so every hover: and
 * group-hover: rule only exists inside @media (hover: hover) and (pointer:
 * fine). A control hidden until its row is hovered (`opacity-0
 * group-hover:opacity-100`) would then never appear on a phone, while staying
 * tappable: Notebook block move/delete, PlanEditor edit / + sub / remove,
 * ProjectTree pin. index.css adds the other half.
 *
 * This compiles src/index.css through Tailwind with the real config and plays
 * the cascade for that one element (rules in source order, specificity,
 * media) on two devices: a phone (hover: none, pointer: coarse) and a desktop
 * (hover: hover, pointer: fine). Against 12fac9a10 (no fallback) the phone and
 * keyboard cases resolve to opacity 0.
 */
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import postcss, { type AtRule, type Rule } from "postcss";
import tailwindcss from "tailwindcss";
import { beforeAll, describe, expect, it } from "vitest";

const here = dirname(fileURLToPath(import.meta.url));
const APP = join(here, "..", "..");
const cssPath = process.env.INDEX_CSS ?? join(APP, "src", "index.css");
const twModule = createRequire(import.meta.url)(process.env.TAILWIND_CONFIG ?? join(APP, "tailwind.config.js"));
const config = twModule.default ?? twModule;

const REVEAL = "opacity-0 group-hover:opacity-100";
type Device = { hover: "hover" | "none"; pointer: "fine" | "coarse" };
const PHONE: Device = { hover: "none", pointer: "coarse" };
const DESKTOP: Device = { hover: "hover", pointer: "fine" };
type State = { hover: boolean; focusWithin: boolean };

/** Evaluate the media query lists this sheet uses: `[not all and] (f: v) [and (f: v)]*`, comma = or. */
function mediaMatches(params: string, d: Device): boolean {
  return params.split(",").some((q) => {
    const neg = /^\s*not all and /.test(q);
    const feats = [...q.matchAll(/\(\s*([a-z-]+)\s*:\s*([a-z-]+)\s*\)/g)];
    if (!feats.length) return !neg; // e.g. print/screen-free queries this test does not model
    const all = feats.every(([, f, v]) => (f === "hover" ? d.hover === v : f === "pointer" ? d.pointer === v : false));
    return neg ? !all : all;
  });
}

/** Does `sel` match the revealing element, a child of `.group`, in this state? */
function matches(sel: string, s: State): boolean {
  const esc = (c: string) => c.replace(/:/g, "\\:");
  const self = sel.trim().split(/\s+/).pop()!;
  const selfOk = REVEAL.split(" ").some((c) => self === `.${esc(c)}`);
  if (!selfOk) return false;
  const ancestor = sel.trim().split(/\s+/).slice(0, -1).join(" ");
  if (!ancestor) return true;
  if (ancestor === ".group:hover") return s.hover;
  if (ancestor === ".group:focus-within") return s.focusWithin;
  return false;
}
/** Classes + pseudo-classes (all this sheet uses for the element): escaped `\:` is part of a class name. */
const specificity = (sel: string) => (sel.replace(/\\./g, "x").match(/\.|:(?!:)/g) ?? []).length;

/** The opacity the revealing element ends with. */
function opacity(css: postcss.Root, d: Device, s: State): string {
  const applied: Array<{ spec: number; order: number; value: string }> = [];
  let order = 0;
  css.walkRules((rule: Rule) => {
    order++;
    for (let p = rule.parent; p && p.type === "atrule"; p = p.parent) {
      const at = p as AtRule;
      if (at.name === "media" && !mediaMatches(at.params, d)) return;
    }
    const values: string[] = [];
    rule.walkDecls("opacity", (decl) => void values.push(decl.value));
    if (!values.length) return;
    for (const sel of rule.selectors) {
      if (matches(sel, s)) applied.push({ spec: specificity(sel), order, value: values[values.length - 1] });
    }
  });
  // The winner: highest specificity, then the last in source order.
  applied.sort((a, b) => a.spec - b.spec || a.order - b.order);
  return applied.at(-1)?.value ?? "1";
}

let sheet: postcss.Root;
beforeAll(async () => {
  const raw = [{ raw: `<div class="group"><button class="${REVEAL}">remove</button></div>`, extension: "html" }];
  const out = await postcss([tailwindcss({ ...config, content: raw })]).process(readFileSync(cssPath, "utf8"), { from: cssPath });
  sheet = out.root;
});

describe("hover-revealed controls (opacity-0 group-hover:opacity-100)", () => {
  it("desktop: hidden at rest, shown on hover (the flag still scopes hover)", () => {
    expect(opacity(sheet, DESKTOP, { hover: false, focusWithin: false })).toBe("0");
    expect(opacity(sheet, DESKTOP, { hover: true, focusWithin: false })).toBe("1");
  });

  it("phone: shown, since no hover ever fires there", () => {
    expect(opacity(sheet, PHONE, { hover: false, focusWithin: false })).toBe("1");
  });

  it("keyboard: shown while the row holds focus, on any device", () => {
    expect(opacity(sheet, DESKTOP, { hover: false, focusWithin: true })).toBe("1");
    expect(opacity(sheet, PHONE, { hover: false, focusWithin: true })).toBe("1");
  });

  it("the hover rule really is inside the hover media query (else the phone case proves nothing)", () => {
    let wrapped = false;
    sheet.walkRules((rule) => {
      if (rule.selector.includes(".group:hover .group-hover\\:opacity-100")) {
        const at = rule.parent as AtRule;
        wrapped = at?.type === "atrule" && /\(hover: ?hover\) and \(pointer: ?fine\)/.test(at.params);
      }
    });
    expect(wrapped).toBe(true);
  });
});
