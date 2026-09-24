import type { ReactNode } from "react";

/**
 * LemonTable — generic-over-Row table. Sticky header optional, row click
 * optional, empty state slot. Replaces hand-rolled tables in Sources,
 * PayoutsAudit, OutcomesIndex, NotebooksIndex, etc.
 *
 *   <LemonTable<Investigation>
 *     rows={rows}
 *     columns={[
 *       { key: "title", header: "Title",  render: (r) => r.title, width: "40%" },
 *       { key: "status", header: "Status", render: (r) => r.status },
 *     ]}
 *     rowKey={(r) => r.id}
 *     onRowClick={(r) => navigate(`/inv/${r.id}`)}
 *   />
 */
export type LemonColumn<Row> = {
  key: string;
  header: ReactNode;
  render: (row: Row, i: number) => ReactNode;
  width?: string;
  align?: "left" | "right" | "center";
};

type Props<Row> = {
  rows: Row[];
  columns: LemonColumn<Row>[];
  rowKey: (row: Row, i: number) => string;
  onRowClick?: (row: Row) => void;
  emptyState?: ReactNode;
  stickyHeader?: boolean;
  className?: string;
  /** Compact paddings for dense data views. */
  dense?: boolean;
};

// Literal class names so Tailwind's scanner sees all three (a built
// `text-${align}` only rendered where another file happened to use it).
const ALIGN = { left: "text-left", right: "text-right", center: "text-center" } as const;

export function LemonTable<Row>({
  rows,
  columns,
  rowKey,
  onRowClick,
  emptyState,
  stickyHeader = false,
  dense = false,
  className = "",
}: Props<Row>) {
  const cellY = dense ? "py-1.5" : "py-2.5";
  return (
    <div
      // Flat and bounded like a card (design spec §4); the header is a quiet
      // inset eyebrow row, not an ink bar lettered in sun (the sun is spent on
      // the one primary action, not on every table).
      className={
        "border border-rule rounded-hog overflow-hidden bg-card " +
        className
      }
    >
      <table className="w-full border-collapse text-sm">
        <thead className={stickyHeader ? "sticky top-0 z-10" : undefined}>
          <tr>
            {columns.map((c) => (
              <th
                key={c.key}
                style={c.width ? { width: c.width } : undefined}
                className={
                  "bg-inset text-2 font-mono text-xs uppercase tracking-wider font-semibold " +
                  `px-3 ${cellY} ${ALIGN[c.align ?? "left"]} ` +
                  "border-b border-rule"
                }
              >
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td
                colSpan={columns.length}
                className="px-3 py-8 text-center text-ink-mute dark:text-moonlight italic"
              >
                {emptyState ?? "No rows."}
              </td>
            </tr>
          ) : (
            rows.map((row, i) => (
              <tr
                key={rowKey(row, i)}
                onClick={onRowClick ? () => onRowClick(row) : undefined}
                className={
                  "border-b border-hairline last:border-b-0 text-1 " +
                  (onRowClick ? "cursor-pointer hover:bg-wash" : "")
                }
              >
                {columns.map((c) => (
                  <td
                    key={c.key}
                    className={`px-3 ${cellY} ${ALIGN[c.align ?? "left"]} align-top`}
                  >
                    {c.render(row, i)}
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}

export default LemonTable;
