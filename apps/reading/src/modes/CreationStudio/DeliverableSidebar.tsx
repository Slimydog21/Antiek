import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import {
  createDeliverable,
  listDeliverables,
  type DeliverableKind,
  type DeliverableSummary,
} from "../../lib/api";
import { emitWernerExperience } from "../../werner/reactionBus";
import { VoiceNoteCapture } from "./VoiceNoteCapture";

const DELIVERABLE_KIND_LABELS: Record<DeliverableKind, string> = {
  research_memo: "Research memo",
  book_chapter: "Book chapter",
  biography_section: "Biography section",
  investor_brief: "Investor brief",
  general_essay: "General essay",
};

/**
 * The CreationStudio's left-rail panel — deliverable list + new-
 * deliverable form + voice-note capture widget. S10 acceptance:
 * "left = block palette panel" (we put the deliverable list on the
 * left because the operator-level navigation needs it more than the
 * block palette does; the palette moves to the right dock).
 *
 * Extracted from index.tsx as its own file so the PanelRegistry can
 * register it as `PanelKind = "DeliverableSidebar"` without a
 * circular dep through the CreationStudio main slot.
 */
export default function DeliverableSidebar() {
  const navigate = useNavigate();
  const [deliverables, setDeliverables] = useState<DeliverableSummary[]>([]);
  const [creating, setCreating] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const [newKind, setNewKind] = useState<DeliverableKind>("research_memo");

  async function refresh() {
    try {
      const { deliverables } = await listDeliverables();
      setDeliverables(deliverables);
    } catch {
      // ignore — show empty
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!newTitle.trim()) return;
    setCreating(true);
    try {
      const d = await createDeliverable({
        title: newTitle.trim(),
        deliverable_kind: newKind,
      });
      setNewTitle("");
      await refresh();
      // Living-TV: new deliverable started — happy craft beat.
      emitWernerExperience("piece_started");
      navigate(`/create/${d.deliverable_id}`);
    } catch {
      emitWernerExperience("fail");
    } finally {
      setCreating(false);
    }
  }

  return (
    <aside className="flex flex-col gap-4 min-h-0 h-full p-3">
      <h2 className="text-sm font-semibold text-ink dark:text-bright">
        Deliverables
      </h2>
      <form
        onSubmit={handleCreate}
        className="bg-ice-0 dark:bg-charcoal-2 border border-rule dark:border-charcoal-1 rounded-md p-3 space-y-2"
      >
        <input
          value={newTitle}
          onChange={(e) => setNewTitle(e.target.value)}
          placeholder="New deliverable title…"
          className="w-full px-2 py-1.5 text-sm border border-rule dark:border-charcoal-1 rounded focus:outline-none focus:ring-2 focus:ring-sun"
        />
        <select
          value={newKind}
          onChange={(e) => setNewKind(e.target.value as DeliverableKind)}
          className="w-full px-2 py-1.5 text-xs border border-rule dark:border-charcoal-1 rounded focus:outline-none focus:ring-2 focus:ring-sun"
        >
          {(Object.keys(DELIVERABLE_KIND_LABELS) as DeliverableKind[]).map(
            (k) => (
              <option key={k} value={k}>
                {DELIVERABLE_KIND_LABELS[k]}
              </option>
            ),
          )}
        </select>
        <button
          type="submit"
          disabled={creating || !newTitle.trim()}
          className="w-full px-3 py-1.5 bg-ink hover:bg-shadow-2 disabled:bg-glacial-1 dark:bg-slate-1 text-white text-xs font-medium rounded transition-colors"
        >
          {creating ? "Creating…" : "New deliverable"}
        </button>
      </form>
      <ul className="flex-1 overflow-y-auto space-y-1 min-h-0">
        {deliverables.map((d) => (
          <li key={d.deliverable_id}>
            <button
              onClick={() => navigate(`/create/${d.deliverable_id}`)}
              className="w-full text-left px-3 py-2 bg-ice-0 dark:bg-charcoal-2 hover:bg-ice-3 dark:bg-charcoal-1 border border-rule dark:border-charcoal-1 rounded text-sm"
            >
              <div className="font-medium truncate">{d.title}</div>
              <div className="text-xs text-shadow-1 dark:text-moonlight flex justify-between">
                <span>
                  {DELIVERABLE_KIND_LABELS[d.deliverable_kind] ??
                    d.deliverable_kind}
                </span>
                <span>{d.section_count} §</span>
              </div>
            </button>
          </li>
        ))}
      </ul>
      <VoiceNoteCapture />
    </aside>
  );
}
