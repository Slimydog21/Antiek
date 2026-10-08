/**
 * ProductsLauncher — the flag gate (SPR-01 pane-flow packet).
 *
 * The packet rewrote the launcher's SURFACE (grouped grid → flat ranked
 * list, rounded → rounded-none, sun border-l-2 active treatment). That
 * restyle was ungated and red on the shell-products-launcher--open visual
 * baselines, so the design verdict is: the restyle rides the
 * `antiek.flag.pane.flow` flag like the rest of the packet, and the
 * flag-off path is main's launcher, byte-verbatim (ProductsLauncherLegacy
 * is origin/main's file untouched — old behavior included; the flow
 * build's IME/modifier guards, activeId selection, scrollIntoView and
 * exhaustive activate stay flag-on only, so there are two surfaces to
 * review, not three).
 *
 * Consumers keep importing `{ ProductsLauncher }` from this module and get
 * the switch; the two implementations never import each other.
 */
import { isFeatureOn } from "../lib/featureFlags";
import ProductsLauncherLegacy from "./ProductsLauncherLegacy";
import ProductsLauncherFlow from "./ProductsLauncherFlow";

export function ProductsLauncher({ open, onClose }: { open: boolean; onClose: () => void }) {
  return isFeatureOn("pane.flow") ? (
    <ProductsLauncherFlow open={open} onClose={onClose} />
  ) : (
    <ProductsLauncherLegacy open={open} onClose={onClose} />
  );
}

export default ProductsLauncher;
