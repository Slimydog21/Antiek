import { Fragment, useEffect, useMemo, useRef, useState } from "react";

import { LemonModal } from "../lemon/LemonModal";
import { readCustomHotkeys } from "../../workspace/persistence";
import { formatBinding } from "./bindings";
import { NOTES, TASK_OF, TASK_TITLES, comboParts } from "./keymapView";
import {
  ACTIONS,
  KEYMAP,
  currentPlatform,
  isActiveOn,
  readPrefix,
  type ActionId,
  type ActionMeta,
  type KeymapRow,
  type KeymapTask,
  type Platform,
} from "./keymap";

import "./KeySheet.css";

/**
 * KeySheet — every key the app answers to, rendered from keymap.ts (`?` or
 * prefix+?). Lazy-loaded by HotkeyHud, so it costs the entry chunk nothing.
 *
 * Grouped by task. Each action shows its prefix form and its direct form
 * side by side. `/` moves to the filter (as in herdr's keybind help), ctrl+u
 * clears it, Esc closes the sheet and HotkeyHud returns focus to where it
 * was. Every row carries `data-keymap-row` so a test can prove that no table
 * row is missing from the sheet.
 */
export interface KeySheetProps {
  onClose: () => void;
  /** Test/story seam: render another platform's keys. */
  platform?: Platform;
}

interface ActionEntry {
  action: ActionId;
  meta: ActionMeta;
  prefixRows: KeymapRow[];
  directRows: KeymapRow[];
}

const TASK_ORDER: KeymapTask[] = ["find", "go", "panels", "help"];

function Keys({ parts }: { parts: string[] }) {
  return (
    <span className="antiek-keysheet__keys">
      {parts.map((p, i) => (
        <kbd key={i} className="antiek-keysheet__key">
          {p}
        </kbd>
      ))}
    </span>
  );
}

function searchText(entry: ActionEntry, prefix: string, platform: Platform): string {
  const forms = [
    ...entry.prefixRows.map((r) => [...comboParts(prefix, platform), ...comboParts(r.prefixKey!, platform)].join(" ")),
    ...entry.directRows.map((r) => comboParts(r.chord!, platform).join(" ")),
    ...entry.prefixRows.map((r) => `prefix ${r.prefixKey}`),
    ...entry.directRows.map((r) => r.chord!),
  ];
  return [entry.meta.label, NOTES[entry.action] ?? "", TASK_TITLES[TASK_OF[entry.action]], ...forms]
    .join(" ")
    .toLowerCase();
}

export default function KeySheet({ onClose, platform = currentPlatform() }: KeySheetProps) {
  const [filter, setFilter] = useState("");
  const filterRef = useRef<HTMLInputElement>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const prefix = readPrefix();

  const groups = useMemo(() => {
    const byAction = new Map<ActionId, ActionEntry>();
    for (const row of KEYMAP) {
      if (!isActiveOn(row, platform)) continue;
      const entry =
        byAction.get(row.action) ??
        ({ action: row.action, meta: ACTIONS[row.action], prefixRows: [], directRows: [] } as ActionEntry);
      if (row.prefixKey) entry.prefixRows.push(row);
      if (row.chord) entry.directRows.push(row);
      byAction.set(row.action, entry);
    }
    return TASK_ORDER.map((task) => ({
      task,
      entries: [...byAction.values()].filter((e) => TASK_OF[e.action] === task),
    })).filter((g) => g.entries.length > 0);
  }, [platform]);

  const custom = useMemo(() => readCustomHotkeys().bindings, []);

  const needle = filter.trim().toLowerCase();
  const visible = needle
    ? groups
        .map((g) => ({ ...g, entries: g.entries.filter((e) => searchText(e, prefix, platform).includes(needle)) }))
        .filter((g) => g.entries.length > 0)
    : groups;
  const visibleCustom = needle
    ? custom.filter((c) => `${c.label} ${formatBinding(c.spec)} ${c.spec}`.toLowerCase().includes(needle))
    : custom;

  // `/` jumps to the filter from anywhere in the dialog (the close button
  // holds focus when it opens); ctrl+u clears the filter. Scoped to this
  // dialog element: it claims no global key.
  useEffect(() => {
    const dialog = rootRef.current?.closest<HTMLElement>('[role="dialog"]');
    if (!dialog) return;
    const onKey = (e: KeyboardEvent) => {
      const input = filterRef.current;
      if (!input) return;
      if (e.key === "/" && e.target !== input && !e.metaKey && !e.ctrlKey && !e.altKey) {
        e.preventDefault();
        input.focus();
      } else if (e.key.toLowerCase() === "u" && e.ctrlKey && e.target === input) {
        e.preventDefault();
        setFilter("");
      }
    };
    dialog.addEventListener("keydown", onKey);
    return () => dialog.removeEventListener("keydown", onKey);
  }, []);

  const prefixParts = comboParts(prefix, platform);

  return (
    <LemonModal open onClose={onClose} title="Keyboard shortcuts" size="lg">
      <div ref={rootRef} className="antiek-keysheet" data-keymap-owner="keysheet.toggle">
        <p className="antiek-keysheet__intro">
          Press <Keys parts={prefixParts} />, then a key. The prefix waits for that key or Esc; it never times
          out. Or use a direct key, with no prefix.
        </p>

        <label className="antiek-keysheet__filter">
          <span className="antiek-keysheet__filter-label">Filter</span>
          <input
            ref={filterRef}
            type="search"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            aria-label="Filter shortcuts"
            placeholder="Type to filter"
            className="antiek-keysheet__filter-input"
          />
          <span className="antiek-keysheet__filter-hint" aria-hidden="true">
            <Keys parts={["/"]} />
          </span>
        </label>

        {visible.length === 0 && visibleCustom.length === 0 && (
          <p className="antiek-keysheet__empty" role="status">
            No shortcut matches &ldquo;{filter}&rdquo;.
          </p>
        )}

        {visible.map((g) => (
          <section key={g.task} className="antiek-keysheet__group" aria-labelledby={`keysheet-${g.task}`}>
            <h3 id={`keysheet-${g.task}`} className="antiek-keysheet__heading">
              {TASK_TITLES[g.task]}
            </h3>
            <table className="antiek-keysheet__table">
              <thead>
                <tr>
                  <th scope="col">Action</th>
                  <th scope="col">After the prefix</th>
                  <th scope="col">Direct</th>
                </tr>
              </thead>
              <tbody>
                {g.entries.map((e) => (
                  <tr key={e.action} data-keymap-action={e.action}>
                    <th scope="row" className="antiek-keysheet__label">
                      {e.meta.label}
                      {NOTES[e.action] && <span className="antiek-keysheet__note">{NOTES[e.action]}</span>}
                    </th>
                    <td className="antiek-keysheet__forms" data-column="After the prefix">
                      {e.prefixRows.length === 0 ? (
                        <span className="antiek-keysheet__none">none</span>
                      ) : (
                        e.prefixRows.map((r) => (
                          <span key={r.id} className="antiek-keysheet__form" data-keymap-row={r.id}>
                            <Keys parts={prefixParts} />
                            <span className="antiek-keysheet__then" aria-hidden="true">
                              ›
                            </span>
                            <Keys parts={comboParts(r.prefixKey!, platform)} />
                          </span>
                        ))
                      )}
                    </td>
                    <td className="antiek-keysheet__forms" data-column="Direct">
                      {e.directRows.length === 0 ? (
                        <span className="antiek-keysheet__none">none</span>
                      ) : (
                        e.directRows.map((r, i) => (
                          <Fragment key={r.id}>
                            {i > 0 && <span className="antiek-keysheet__or">or</span>}
                            <span className="antiek-keysheet__form" data-keymap-row={r.id}>
                              <Keys parts={comboParts(r.chord!, platform)} />
                            </span>
                          </Fragment>
                        ))
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        ))}

        <section className="antiek-keysheet__group" aria-labelledby="keysheet-custom">
          <h3 id="keysheet-custom" className="antiek-keysheet__heading">
            Your custom hotkeys
          </h3>
          {custom.length === 0 ? (
            <p className="antiek-keysheet__empty">You haven&apos;t assigned any custom hotkeys yet.</p>
          ) : (
            <ul className="antiek-keysheet__custom">
              {visibleCustom.map((c) => (
                <li key={c.id} className="antiek-keysheet__custom-row">
                  <span>{c.label}</span>
                  <Keys parts={comboParts(c.spec, platform)} />
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </LemonModal>
  );
}
