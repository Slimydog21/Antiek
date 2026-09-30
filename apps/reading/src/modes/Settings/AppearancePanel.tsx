import LemonCard from "../../components/lemon/LemonCard";
import { LemonSelect } from "../../components/lemon";
import type { MotionPreference, ThemePreference } from "../../design/theme";
import { useMotionPreference, useTheme } from "../../design/useTheme";

const THEMES: Array<{ value: ThemePreference; label: string }> = [
  { value: "system", label: "System" },
  { value: "light", label: "Light" },
  { value: "dark", label: "Dark" },
];

const MOTIONS: Array<{ value: MotionPreference; label: string }> = [
  { value: "system", label: "System" },
  { value: "reduce", label: "Reduce" },
  { value: "full", label: "Full" },
];

/**
 * Settings > Appearance: the theme (light / dark / system) and motion
 * (system / reduce / full) preferences. Both apply at once, persist per
 * browser, and follow the device while set to System.
 */
export default function AppearancePanel() {
  const theme = useTheme();
  const motion = useMotionPreference();
  return (
    <LemonCard title="Appearance" elevation="z1">
      <div className="grid gap-5 p-4 sm:grid-cols-2">
        <div className="grid content-start gap-1.5">
          <span className="text-sm font-medium text-1">Theme</span>
          <LemonSelect value={theme.preference} onChange={theme.setPreference} options={THEMES} aria-label="Theme" fullWidth />
          <p className="text-xs text-3" data-testid="appearance-theme-hint">
            {theme.preference === "system"
              ? `Follows your device. ${theme.isDark ? "Dark" : "Light"} right now.`
              : `${theme.isDark ? "Dark" : "Light"} in this browser, whatever your device uses.`}
          </p>
        </div>
        <div className="grid content-start gap-1.5">
          <span className="text-sm font-medium text-1">Motion</span>
          <LemonSelect value={motion.preference} onChange={motion.setPreference} options={MOTIONS} aria-label="Motion" fullWidth />
          <p className="text-xs text-3" data-testid="appearance-motion-hint">
            {motion.preference === "full"
              ? "Animations stay on, even if your device asks for less motion."
              : motion.preference === "reduce"
                ? "Transitions are instant and the scene holds still."
                : `Follows your device. ${motion.reduced ? "Motion is reduced" : "Animations are on"} right now.`}
          </p>
        </div>
      </div>
    </LemonCard>
  );
}
