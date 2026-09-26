/**
 * tabStripParts.tsx — the small shared pieces of the document tab strip:
 * the kind glyph, the number + label pair, and the DOM ids the ARIA wiring
 * uses. Presentational only.
 */
import { BookOpen, Bot, FileText, Flag, MessagesSquare, Pilcrow, Search } from "lucide-react";

import { sectionIdFromRef } from "./sectionRef";
import type { TabLabel } from "./tabLabels";
import type { TabNode } from "./tabTree";

export { DOCUMENT_PANEL_ID } from "./documentPanel";

/** A valid, collision-free DOM id for a tab id (tab ids carry ':' and '/'). */
export function domIdFor(prefix: string, tabId: string): string {
  return `${prefix}-${tabId.replace(/[^A-Za-z0-9-]/g, (c) => `_${c.charCodeAt(0).toString(36)}_`)}`;
}

export function KindGlyph({ tab, className = "" }: { tab: Pick<TabNode, "kind" | "ref">; className?: string }) {
  const props = { size: 12, strokeWidth: 1.75, "aria-hidden": true as const, className: `shrink-0 ${className}` };
  switch (tab.kind) {
    case "reader":
      return <BookOpen {...props} />;
    case "research":
      return <Search {...props} />;
    case "document":
      return sectionIdFromRef(tab.ref) !== null ? <Pilcrow {...props} /> : <FileText {...props} />;
    case "thread":
      return <MessagesSquare {...props} />;
    case "companion":
      return <Bot {...props} />;
    case "flags":
      return <Flag {...props} />;
    default:
      return null;
  }
}

/** A hierarchical number short enough to sit beside a label: past three
 *  levels it keeps the root and the last two (`1…4.2` for 1.1.1.1.4.2). The
 *  full number stays the accessible text and the tooltip; the switcher
 *  takes the full number. */
export function compactHier(hier: string): string {
  const segs = hier.split(".");
  return segs.length <= 3 ? hier : `${segs[0]}…${segs.slice(-2).join(".")}`;
}

/** "1.3.2  Lyell, Principles" — the number is the address, the label the
 *  name. A label still being looked up renders quieter, never as an id. */
export function NumberedLabel({
  tab,
  label,
  className = "",
}: {
  tab: TabNode;
  label: TabLabel;
  className?: string;
}) {
  const quiet = label.source === "fallback" || label.pending;
  const short = compactHier(tab.hier_number);
  return (
    <>
      <span
        className="font-mono tabular-nums text-shadow-1 dark:text-moonlight shrink-0"
        title={short === tab.hier_number ? undefined : tab.hier_number}
      >
        {short === tab.hier_number ? (
          short
        ) : (
          <>
            <span aria-hidden="true">{short}</span>
            <span className="sr-only">{tab.hier_number}</span>
          </>
        )}
      </span>
      <span
        className={`truncate ${quiet ? "text-ink-soft dark:text-moonlight" : ""} ${className}`}
        title={label.pending ? `${label.text} (looking up the title…)` : label.text}
      >
        {label.text}
      </span>
    </>
  );
}
