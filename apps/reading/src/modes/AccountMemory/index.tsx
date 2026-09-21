import { useCallback, useEffect, useMemo, useState } from "react";

import {
  buildCorrection,
  fetchAccountMemory,
  foldMemoryVersions,
  formatProvenance,
  memoryKey,
  parseSubstrateTimestamp,
  supersededLocally,
  writeAccountMemory,
  type AccountMemoryItem,
} from "../../api/accountMemory";

/**
 * Account memory — the owner-private long-term store, made visible and editable.
 *
 * SPR-11 Task 6. The substrate half of this has been finished and deployed for
 * weeks: `GET /account/memory` and `POST /account/memory` are mounted, gated on
 * a distinct signed session owner, and the recalled items are injected into the
 * thought-partner prompt on every turn. Until this page there was no caller in
 * `apps/` for either route, so the facts an account accumulated were invisible
 * to the person they were about and correctable only by curl.
 *
 * WHAT IS ON SCREEN, AND WHY EACH PART IS.
 *
 *   subject / predicate / object — the row shape the store actually has
 *     (substrate/memory/models.py). Showing a rendered sentence instead would
 *     hide the key, and the key is what a correction has to target.
 *
 *   valid_from — memory here is bi-temporal. A fact is not simply "true"; it is
 *     true from an instant, and the instant is how two versions are ordered.
 *
 *   provenance — the validator refuses a memory whose provenance carries no
 *     source reference, which makes "where did this come from" answerable for
 *     every row. It is shown inline rather than behind a disclosure, because a
 *     fact the owner cannot trace is a fact they cannot judge.
 *
 *   earlier versions — collapsed under their current head, never hidden.
 *     Nothing in this store is ever deleted: a correction closes the prior edge
 *     with `valid_until` and `superseded_by` and writes a new one. A panel that
 *     dropped the closed row would misrepresent a durable, append-only store as
 *     an editable field.
 *
 * WHERE EARLIER VERSIONS COME FROM. `GET /account/memory` returns only current
 * heads — `recall_memory` -> `list_memory` with the default
 * `include_invalidated=False`, and the route exposes no parameter to change it.
 * So on a cold load this page shows heads and reports no history, which is an
 * honest statement of what the API told it. When the owner corrects a fact here,
 * the row that was just closed is retained and stamped with exactly the closure
 * the substrate performed, so it stays reachable under its replacement. That
 * retention lives in the browser, not the server: a reload re-reads heads only.
 * Closing that gap needs an `include_invalidated` parameter on the GET route,
 * which is backend work and deliberately out of this task's scope.
 */

/** Route ceiling. `get_account_memory` 422s above this. */
const LIST_LIMIT = 50;

function formatTimestamp(value: string | null): string {
  if (!value) return "—";
  const parsed = parseSubstrateTimestamp(value);
  if (!parsed) return value;
  return parsed.toISOString().replace("T", " ").replace(/\.\d+Z$/, "Z");
}

export default function AccountMemory() {
  /** Every row the panel knows about: server heads, plus versions it watched a
   *  correction close. `foldMemoryVersions` sorts out which is which. */
  const [rows, setRows] = useState<AccountMemoryItem[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [editingKey, setEditingKey] = useState<string | null>(null);
  const [draftObject, setDraftObject] = useState<string>("");
  const [draftNote, setDraftNote] = useState<string>("");
  const [submitting, setSubmitting] = useState<boolean>(false);

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetchAccountMemory({ limit: LIST_LIMIT });
      setRows((previous) => {
        // Keep the superseded versions this session has seen; the server would
        // otherwise drop them on every refresh and the collapsed history would
        // silently empty itself.
        const retained = previous.filter((row) => row.valid_to !== null);
        return [...retained, ...response.items];
      });
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  const groups = useMemo(() => foldMemoryVersions(rows), [rows]);

  const beginCorrection = (key: string, currentObject: string) => {
    setEditingKey(key);
    setDraftObject(currentObject);
    setDraftNote("");
    setNotice(null);
    setError(null);
  };

  const cancelCorrection = () => {
    setEditingKey(null);
    setDraftObject("");
    setDraftNote("");
  };

  const submitCorrection = async (head: AccountMemoryItem) => {
    const next = draftObject.trim();
    if (!next || submitting) return;
    setSubmitting(true);
    setError(null);
    setNotice(null);
    try {
      const response = await writeAccountMemory(
        buildCorrection(head, next, { note: draftNote }),
      );
      if (response.action === "NOOP") {
        setNotice(
          `No change written — "${head.subject} ${head.predicate}" already reads that way.`,
        );
      } else {
        setRows((previous) => {
          const key = memoryKey(head);
          const kept = previous.map((row) =>
            row.edge_id === head.edge_id && memoryKey(row) === key
              ? supersededLocally(row, response.item)
              : row,
          );
          return [...kept, response.item];
        });
        setNotice(
          response.action === "SUPERSEDE"
            ? "Corrected. The previous value is kept below its replacement."
            : `Recorded (${response.action}).`,
        );
      }
      cancelCorrection();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="flex flex-col h-screen">
      <main
        className="flex-1 overflow-y-auto bg-ice-0 dark:bg-charcoal-2"
        data-testid="memory-panel"
      >
        <div className="max-w-3xl mx-auto px-8 py-10 space-y-6">
          <header className="space-y-2">
            <h1 className="text-2xl font-serif text-ink dark:text-bright">
              Account memory
            </h1>
            <p className="text-sm text-shadow-1 dark:text-starlight leading-relaxed">
              What Antiek remembers about you, in the shape it is actually stored:
              a subject, a predicate and an object, valid from an instant, with the
              provenance that earned it a place here. These facts are read into the
              thought partner&apos;s context on every turn. Nothing is deleted —
              correcting a fact writes a new version and keeps the old one, shown
              collapsed beneath its replacement.
            </p>
          </header>

          {error && (
            <p
              className="text-sm text-emperor border border-red-200 bg-red-50 px-3 py-2 rounded"
              data-testid="memory-error"
              role="alert"
            >
              {error}
            </p>
          )}

          {notice && !error && (
            <p
              className="text-sm text-emerald-700 border border-emerald-200 bg-emerald-50 px-3 py-2 rounded"
              data-testid="memory-notice"
              role="status"
            >
              {notice}
            </p>
          )}

          {loading && rows.length === 0 && (
            <p
              className="text-sm italic text-shadow-1 dark:text-moonlight"
              data-testid="memory-loading"
            >
              Reading your memory…
            </p>
          )}

          {!loading && groups.length === 0 && !error && (
            <p
              className="text-sm italic text-shadow-1 dark:text-moonlight"
              data-testid="memory-empty"
            >
              Nothing remembered yet. Facts arrive from ingested documents and,
              once the interaction extractor is switched on, from conversations.
            </p>
          )}

          <ul className="space-y-4">
            {groups.map((group) => {
              const editing = editingKey === group.key;
              // Subject and predicate go on the element as two separate
              // attributes rather than as the joined key: the key is NUL-joined
              // (both halves are free text, so no printable separator is safe)
              // and a NUL does not survive a DOM attribute selector.
              return (
                <li
                  key={group.key}
                  data-testid="memory-row"
                  data-memory-subject={group.subject}
                  data-memory-predicate={group.predicate}
                  className="border border-rule dark:border-charcoal-1 rounded-md p-5 space-y-3"
                >
                  <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
                    <code
                      className="text-xs font-mono text-shadow-1 dark:text-moonlight"
                      data-testid="memory-subject"
                    >
                      {group.subject}
                    </code>
                    <code
                      className="text-xs font-mono text-sun-deep"
                      data-testid="memory-predicate"
                    >
                      {group.predicate}
                    </code>
                  </div>

                  <p
                    className="text-base font-serif text-ink dark:text-bright break-words"
                    data-testid="memory-object"
                  >
                    {group.head.object}
                  </p>

                  <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs">
                    <dt className="text-shadow-1 dark:text-moonlight uppercase tracking-wider">
                      valid from
                    </dt>
                    <dd
                      className="font-mono text-shadow-1 dark:text-starlight"
                      data-testid="memory-valid-from"
                    >
                      {formatTimestamp(group.head.valid_from)}
                    </dd>
                    <dt className="text-shadow-1 dark:text-moonlight uppercase tracking-wider">
                      provenance
                    </dt>
                    <dd
                      className="font-mono text-shadow-1 dark:text-starlight break-words"
                      data-testid="memory-provenance"
                    >
                      {formatProvenance(group.head.provenance)}
                    </dd>
                  </dl>

                  {group.superseded.length > 0 && (
                    <details
                      className="border-t border-rule dark:border-charcoal-1 pt-2"
                      data-testid="memory-history"
                    >
                      <summary
                        className="text-[10px] uppercase tracking-wider font-mono text-shadow-1 dark:text-moonlight cursor-pointer"
                        data-testid="memory-history-summary"
                      >
                        {group.superseded.length} earlier{" "}
                        {group.superseded.length === 1 ? "version" : "versions"}
                      </summary>
                      <ul className="mt-2 space-y-2">
                        {group.superseded.map((old) => (
                          <li
                            key={old.edge_id}
                            data-testid="memory-history-item"
                            data-memory-edge-id={old.edge_id}
                            className="border-l-2 border-rule dark:border-charcoal-1 pl-3 space-y-1"
                          >
                            <p
                              className="text-sm text-shadow-1 dark:text-starlight line-through break-words"
                              data-testid="memory-history-object"
                            >
                              {old.object}
                            </p>
                            <p className="text-[11px] font-mono text-shadow-1 dark:text-moonlight">
                              {formatTimestamp(old.valid_from)} →{" "}
                              {formatTimestamp(old.valid_to)}
                            </p>
                            <p
                              className="text-[11px] font-mono text-shadow-1 dark:text-moonlight break-words"
                              data-testid="memory-history-provenance"
                            >
                              {formatProvenance(old.provenance)}
                            </p>
                          </li>
                        ))}
                      </ul>
                    </details>
                  )}

                  {editing ? (
                    <div className="space-y-2 pt-1">
                      <label
                        className="block text-[10px] uppercase tracking-wider font-mono text-shadow-1 dark:text-moonlight"
                        htmlFor={`memory-correct-${group.head.edge_id}`}
                      >
                        corrected value
                      </label>
                      <textarea
                        id={`memory-correct-${group.head.edge_id}`}
                        data-testid="memory-correct-input"
                        value={draftObject}
                        onChange={(e) => setDraftObject(e.target.value)}
                        rows={2}
                        className="w-full text-sm font-serif text-ink dark:text-bright bg-ice-1 dark:bg-charcoal-1 border border-rule dark:border-charcoal-1 rounded px-2 py-1"
                      />
                      <input
                        data-testid="memory-correct-note"
                        aria-label="Reason for the correction"
                        value={draftNote}
                        onChange={(e) => setDraftNote(e.target.value)}
                        placeholder="why (optional — recorded in provenance)"
                        className="w-full text-xs font-mono text-ink dark:text-bright bg-ice-1 dark:bg-charcoal-1 border border-rule dark:border-charcoal-1 rounded px-2 py-1"
                      />
                      <div className="flex gap-2">
                        <button
                          type="button"
                          data-testid="memory-correct-submit"
                          disabled={submitting || !draftObject.trim()}
                          onClick={() => void submitCorrection(group.head)}
                          className="text-[10px] uppercase tracking-wider font-mono border border-rule dark:border-charcoal-1 px-2 py-1 rounded text-ink dark:text-bright disabled:opacity-50"
                        >
                          {submitting ? "saving…" : "save correction"}
                        </button>
                        <button
                          type="button"
                          data-testid="memory-correct-cancel"
                          onClick={cancelCorrection}
                          className="text-[10px] uppercase tracking-wider font-mono px-2 py-1 rounded text-shadow-1 dark:text-moonlight"
                        >
                          cancel
                        </button>
                      </div>
                    </div>
                  ) : (
                    <button
                      type="button"
                      data-testid="memory-correct-button"
                      onClick={() => beginCorrection(group.key, group.head.object)}
                      className="text-[10px] uppercase tracking-wider font-mono border border-rule dark:border-charcoal-1 px-2 py-1 rounded text-ink dark:text-bright"
                    >
                      correct this fact
                    </button>
                  )}
                </li>
              );
            })}
          </ul>

          <footer className="pt-2">
            <button
              type="button"
              data-testid="memory-reload"
              onClick={() => void reload()}
              className="text-[10px] uppercase tracking-wider font-mono text-shadow-1 dark:text-moonlight"
            >
              refresh
            </button>
          </footer>
        </div>
      </main>
    </div>
  );
}
