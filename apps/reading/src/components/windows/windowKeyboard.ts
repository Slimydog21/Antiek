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
