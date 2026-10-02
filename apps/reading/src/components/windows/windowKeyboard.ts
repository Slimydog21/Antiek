import { currentPlatform, KEYMAP, parseCombo } from "../hotkeys/keymap";

type WindowCommand =
  | { kind: "move" | "resize"; dx: number; dy: number }
  | { kind: "toggle" }
  | { kind: "close" };

type WindowBinding = {
  keys: readonly string[];
  shift: boolean;
  kind: WindowCommand["kind"];
  help: string;
};

const ARROWS = ["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"];
const BINDINGS: readonly WindowBinding[] = [
  { keys: ARROWS, shift: false, kind: "move", help: "Arrows move" },
  { keys: ARROWS, shift: true, kind: "resize", help: "Shift+arrows resize" },
  { keys: ["Enter", "f"], shift: false, kind: "toggle", help: "Enter/F full or restore" },
  { keys: ["Escape"], shift: false, kind: "close", help: "Esc close" },
];

export const WINDOW_KEYBOARD_HELP = BINDINGS.map((binding) => binding.help).join(" · ");
export const WINDOW_KEYBOARD_SHORTCUTS = BINDINGS.flatMap((binding) =>
  binding.keys.map((key) => `${binding.shift ? "Shift+" : ""}${key}`),
).join(" ");

export function windowKeyboardHints(flowing: boolean): { help: string; shortcuts: string } {
  if (!flowing) return { help: WINDOW_KEYBOARD_HELP, shortcuts: WINDOW_KEYBOARD_SHORTCUTS };
  const groups: [string[], string][] = [
    [["chord-pane-left-arrow", "chord-pane-right"], "focus"],
    [["chord-pane-reorder-left", "chord-pane-reorder-right"], "reorder"],
    [["chord-layout-preset"], "layout"], [["chord-pane-full"], "zoom"],
  ];
  const shortcuts: string[] = [];
  const help = groups.flatMap(([ids, label]) => {
    const bindings = ids.flatMap((id) => {
      const row = KEYMAP.find((member) => member.id === id);
      if (!row?.chord) return [];
      const combo = parseCombo(row.chord);
      const mods = [combo.ctrl || (combo.mod && currentPlatform() === "other") ? "Control" : "",
        combo.alt ? "Alt" : "", combo.shift ? "Shift" : "",
        combo.meta || (combo.mod && currentPlatform() === "mac") ? "Meta" : ""].filter(Boolean);
      const key = combo.key === "arrowleft" ? "ArrowLeft" : combo.key === "arrowright" ? "ArrowRight" : combo.key.toUpperCase();
      shortcuts.push([...mods, key].join("+"));
      const prefix = mods.map((mod) => mod === "Control" ? "Ctrl" : mod).join("+");
      return [{ prefix: prefix ? prefix + "+" : "", key: key === "ArrowLeft" ? "←" : key === "ArrowRight" ? "→" : key }];
    });
    const first = bindings[0];
    if (!first) return [];
    const keys = bindings.every((binding) => binding.prefix === first.prefix)
      ? first.prefix + bindings.map((binding) => binding.key).join("/")
      : bindings.map((binding) => binding.prefix + binding.key).join("/");
    return [`${keys} ${label}`];
  });
  return { help: [...help, "Enter/F zoom", "Esc restore zoom or close"].join(" · "),
    shortcuts: [...shortcuts, "Enter", "F", "Escape"].join(" ") };
}

export function windowCommand(event: KeyboardEvent): WindowCommand | null {
  if (event.defaultPrevented || event.isComposing || event.ctrlKey || event.metaKey ||
      event.altKey || event.getModifierState("AltGraph")) return null;
  const key = event.key === "F" ? "f" : event.key;
  const binding = BINDINGS.find((item) => item.shift === event.shiftKey && item.keys.includes(key));
  if (!binding) return null;
  if (binding.kind === "toggle" || binding.kind === "close") return { kind: binding.kind };
  switch (key) {
    case "ArrowLeft": return { kind: binding.kind, dx: -24, dy: 0 };
    case "ArrowRight": return { kind: binding.kind, dx: 24, dy: 0 };
    case "ArrowUp": return { kind: binding.kind, dx: 0, dy: -24 };
    case "ArrowDown": return { kind: binding.kind, dx: 0, dy: 24 };
    default: return null;
  }
}
