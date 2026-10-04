import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { resolve } from "node:path";
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";

const out = resolve(process.env.D2_GUARD_EVIDENCE ?? "../../_audit/keymap-mutations");
mkdirSync(out, { recursive: true });
const shortcuts = "src/workspace/shortcuts.ts";
const keymap = "src/components/hotkeys/keymap.ts";
const strip = "src/workspace/DocumentTabStrip.tsx";
const guardFiles = ["scripts/keymap-guard.py", "scripts/keymap-guard.scenarios.ts", "src/workspace/windowKeyListenerCensus.test.ts", "src/workspace/keyboardOwnership.ts", "scripts/keymap-guard-mutations.ts"];
const hash = () => createHash("sha256").update(guardFiles.map((p) => readFileSync(p)).join("\n") + readFileSync(keymap, "utf8").split("export function validateKeymap")[1]).digest("hex");
const gateHash = hash();
interface Mutant { name: string; file: string; from: string; to: string; row?: string; command?: string[]; names: string[]; extra?: { file: string; from: string; to: string }[]; }
const mutants: Mutant[] = [
  { name: "noop-handler", file: shortcuts,
    from: '"projecttree.toggle": () => toggleProjectTree(),', to: '"projecttree.toggle": () => {},',
    row: "chord-sidebar", names: ["chord-sidebar/projecttree.toggle", "visible effect missing"] },
  { name: "remove-owner", file: shortcuts,
    from: '  const removePrefix = registerKeyboardOwner(window, {',
    to: '  const removePrefix = (() => () => {})(window, {',
    row: "prefix-sidebar", names: ["workspace.prefix", "expected one installation"] },
  { name: "second-active-owner", file: shortcuts,
    from: '  window.addEventListener("blur", onBlur);',
    to: `  const removeDuplicate = registerKeyboardOwner(window, {
    id: "workspace.duplicate", scope: "global-direct", eligible: (e) => directCandidate(e) !== null,
  }, onBubble);
  window.addEventListener("blur", onBlur);`,
    row: "chord-sidebar", names: ["workspace.direct", "workspace.duplicate", "key=b context=default"] },
  { name: "unexercised-row", file: keymap,
    from: 'export const KEYMAP: readonly KeymapRow[] = [',
    to: `export const KEYMAP: readonly KeymapRow[] = [
  { id: "mutant-unexercised", action: "mutant.unexercised", chord: "ctrl+alt+z", scope: "anywhere", origin: "legacy-SPR-08", status: "implemented" },`,
    row: "mutant-unexercised", names: ["mutant-unexercised", "mutant.unexercised", "no executable scenario"],
    extra: [
      { file: keymap, from: "export const ACTIONS = {", to: 'export const ACTIONS = {\n  "mutant.unexercised": { label: "Uncovered mutant" },' },
      { file: shortcuts, from: '    "palette.toggle": () => {', to: '    "mutant.unexercised": () => {},\n    "palette.toggle": () => {' },
    ] },
  { name: "declared-gap-gains-handler", file: shortcuts,
    from: '    "project.select": () => toggleProjectPicker(),',
    to: '    "project.select": () => toggleProjectPicker(),\n    "inbox.toggle": () => toggleProjectPicker(),',
    row: "chord-inbox", names: ["chord-inbox/inbox.toggle", "unimplemented action has a handler"] },
  { name: "stale-location-race", file: strip,
    from: 'const current = window.location;',
    to: 'const current = location;',
    command: ["npx", "vitest", "run", "src/workspace/documentTabs.rapidNavigation.test.tsx"],
    names: ["tab.prev", "tab.next", "previous then next", "next then previous"] },
];
let killed = 0;
for (const mutant of mutants) {
  const patches = [mutant, ...(mutant.extra ?? [])];
  const originals = new Map(patches.map((patch) => [patch.file, readFileSync(patch.file, "utf8")]));
  try {
    for (const patch of patches) {
      const before = readFileSync(patch.file, "utf8");
      if (before.split(patch.from).length !== 2) throw new Error(`${mutant.name}: mutation anchor absent or ambiguous: ${patch.from}`);
      writeFileSync(patch.file, before.replace(patch.from, patch.to));
    }
    const command = mutant.command ?? ["browser-harness"];
    const run = spawnSync(command[0], command.slice(1), {
      encoding: "utf8", timeout: 120000,
      input: mutant.command ? undefined : readFileSync("scripts/keymap-guard.py", "utf8"),
      env: { ...process.env, D2_GUARD_ONLY: mutant.row ?? "", D2_GUARD_PLATFORMS: "mac", D2_GUARD_SCOPES: "0", D2_GUARD_RESULT: `${out}/${mutant.name}.json` },
    });
    const text = `${run.stdout ?? ""}\n${run.stderr ?? ""}`;
    writeFileSync(`${out}/${mutant.name}.log`, `exit=${run.status}\n${text}`);
    if (run.status === 0 || run.status === null || run.error || !mutant.names.every((name) => text.includes(name)) || text.includes("FAIL FIXTURE")) {
      throw new Error(`${mutant.name}: not killed by the required named assertion; see ${out}/${mutant.name}.log`);
    }
    console.log(`KILLED ${mutant.name}: ${mutant.names.join(" / ")} (exit ${run.status})`);
    killed++;
  } finally {
    for (const [path, source] of originals) writeFileSync(path, source);
    if (hash() !== gateHash) throw new Error("Mutation changed its acceptance gate");
  }
}
console.log(`SENSITIVITY ${killed}/${mutants.length}; guard sha256=${gateHash}`);
