import { useCallback, useId, useRef, useState } from "react";
import { LemonModal } from "../lemon/LemonModal";
import { useReadingLightPreference, useTheme } from "../../design/useTheme";

const SELECT_CLASS = "w-full rounded border border-rule bg-card px-3 py-2 text-sm text-1";

export function ReadingLightControl() {
  const id = useId();
  const light = useReadingLightPreference();
  return (
    <div className="grid gap-1.5">
      <label htmlFor={id} className="text-sm font-medium text-1">Page light</label>
      <select id={id} value={light.preference} className={SELECT_CLASS}
        onChange={(event) => light.setPreference(event.target.value === "soft" ? "soft" : "standard")}>
        <option value="standard">Standard</option>
        <option value="soft">Softer</option>
      </select>
      <p className="text-xs text-3">For a dim room, try Softer and lower your device brightness.</p>
    </div>
  );
}

export default function ReadingAppearance() {
  const theme = useTheme();
  const id = useId();
  const trigger = useRef<HTMLButtonElement>(null);
  const [open, setOpen] = useState(false);
  const close = useCallback(() => {
    setOpen(false);
    requestAnimationFrame(() => trigger.current?.focus());
  }, []);
  return (
    <>
      <button type="button" ref={trigger} aria-label="Reading appearance" title="Reading appearance"
        aria-haspopup="dialog" aria-expanded={open} onClick={() => setOpen(true)}
        className="shrink-0 rounded border border-rule px-2 py-1 font-serif text-sm text-1 hover:bg-inset">
        Aa
      </button>
      <LemonModal open={open} onClose={close} title="Make yourself comfortable" size="sm">
        <div className="grid gap-4">
          <div className="grid gap-1.5">
            <label htmlFor={id} className="text-sm font-medium text-1">Reading theme</label>
            <select id={id} value={theme.preference} className={SELECT_CLASS} onChange={(event) => {
              const value = event.target.value;
              if (value === "system" || value === "light" || value === "dark") theme.setPreference(value);
            }}>
              <option value="system">Follow device</option>
              <option value="light">Paper</option>
              <option value="dark">Library at night</option>
            </select>
          </div>
          <ReadingLightControl />
          <p className="text-xs text-3">Your highlighter <mark className="antiek-highlight px-1">A9FF17</mark></p>
        </div>
      </LemonModal>
    </>
  );
}
