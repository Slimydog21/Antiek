/**
 * GearSwitchHost.tsx — SPR-04 M5: the entry-safe mount of the geared
 * switch. The entry chunk carries only this: the flag read, the one
 * window listener for SHORTCUT_EVENTS.GEAR_TOGGLE (surface "topbar"; the
 * Topbar is rendered by AppShell on every route, so the open dialog
 * outlives a navigation away from /zen), and one lazy import. Everything
 * that names a contract or a store lives behind `import("./GearSwitch")`.
 *
 * The flag is re-read on every toggle event, so the keymap guard (and an
 * operator in devtools) can turn it on without a reload; with the flag
 * off the host renders nothing and the key is inert.
 */
import { Suspense, lazy, useCallback, useEffect, useState } from "react";

import { isFeatureOn } from "../../lib/featureFlags";
import { SHORTCUT_EVENTS, toggleGearSwitch } from "../shortcuts";

const GearSwitchContent = lazy(() => import("./GearSwitch"));

export interface GearSwitchHostProps {
  surface: "topbar" | "zen";
}

export function GearSwitchHost({ surface }: GearSwitchHostProps) {
  const [on, setOn] = useState(() => isFeatureOn("nav.switcher"));
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (surface !== "topbar") return;
    const onToggle = () => {
      const live = isFeatureOn("nav.switcher");
      setOn(live);
      setOpen((v) => live && !v);
    };
    window.addEventListener(SHORTCUT_EVENTS.GEAR_TOGGLE, onToggle);
    return () => window.removeEventListener(SHORTCUT_EVENTS.GEAR_TOGGLE, onToggle);
  }, [surface]);

  const close = useCallback(() => setOpen(false), []);

  if (!on) return null;
  return (
    <Suspense fallback={null}>
      <GearSwitchContent surface={surface} open={surface === "topbar" ? open : undefined} onToggle={toggleGearSwitch} onClose={close} />
    </Suspense>
  );
}

export default GearSwitchHost;
