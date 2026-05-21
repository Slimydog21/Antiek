let warnedOnce = false;

/**
 * @deprecated Superseded by `AppShell` (S4 of the UI redesign).
 *
 * `AppShell` (`src/AppShell.tsx`) renders the new global chrome:
 *   - `NavRail` — always-visible 60px icon column
 *   - `Topbar`  — breadcrumbs + ⌘K + account
 *   - `PanelLayout` — left/right docks + floating layer + main slot
 *
 * Now that AppShell is wired in `App.tsx`, this component renders
 * NOTHING (returns `null`) so the legacy double-chrome doesn't appear
 * when an unmigrated mode still calls it. The legacy JSX
 * implementation is preserved in the git history at commit a9f4e59
 * (`sprint(0-1-2): foundations…`) and can be restored under a
 * `VITE_ANTIEK_UI=v1` flag during the S12 cutover if rollback is
 * needed. Per `docs/ui_redesign_posthog/sprint_12_visual_regression_release.html`
 * WP-12.4 this file is deleted entirely after one zero-rollback
 * sprint following the `VITE_ANTIEK_UI=v2` cutover.
 *
 * Do NOT use this in new code. New routes wrap their content in
 * `<PanelHost>` (from `src/workspace/PanelHost.tsx`) and let AppShell
 * provide the chrome.
 */
export default function HeaderBar(_props: {
  children?: React.ReactNode;
}): null {
  if (!warnedOnce && import.meta.env.DEV) {
    warnedOnce = true;
    // eslint-disable-next-line no-console
    console.warn(
      "[antiek] HeaderBar is deprecated — superseded by AppShell (S4). " +
        "This call is now a no-op. See " +
        "docs/ui_redesign_posthog/sprint_04_navigation.html.",
    );
  }
  return null;
}
