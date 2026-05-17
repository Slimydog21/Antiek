import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { useInvestigation } from "../../hooks/useInvestigation";
import { recordSpawnRelationship } from "../../hooks/useInvestigationTree";
import { startInvestigation } from "../../lib/api";
import TrajectoryView from "./TrajectoryView";

/**
 * Right-side slide-over panel for the chase-this flow.
 *
 * Pre-fills a textarea with the highlighted text. Operator edits to
 * formulate the actual question they want chased, hits Spawn. POSTs
 * `/investigations` with parent metadata. After spawn the panel
 * transitions to a live mini TrajectoryView for the child investigation.
 *
 * Dismissing the slide-over does NOT cancel the spawned investigation —
 * it keeps running on the substrate and appears in the sidebar tree.
 * "Open in main view" navigates to /inv/<child-id> in the center pane.
 */
export default function ChaseSlideOver({
  open,
  spawnContext,
  parentInvestigationId,
  onClose,
}: {
  open: boolean;
  spawnContext: string;
  parentInvestigationId: string;
  onClose: () => void;
}) {
  const [question, setQuestion] = useState(spawnContext);
  const [busy, setBusy] = useState(false);
  const [spawnedId, setSpawnedId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  // Reset to fresh state when reopened with a new selection.
  useEffect(() => {
    if (open) {
      setQuestion(spawnContext);
      setSpawnedId(null);
      setError(null);
    }
  }, [open, spawnContext]);

  // ESC to close.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  async function spawn() {
    const q = question.trim();
    if (q.length < 3) {
      setError("Question is too short.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const resp = await startInvestigation({
        question: q,
        context: spawnContext,
        parent_investigation_id: parentInvestigationId,
        spawn_context: spawnContext,
      });
      setSpawnedId(resp.investigation_id);
      recordSpawnRelationship(resp.investigation_id, parentInvestigationId);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-30 bg-stone-900/30 flex justify-end"
      onClick={onClose}
    >
      <div
        className="bg-white w-full max-w-[480px] h-full shadow-2xl flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="px-5 py-3 border-b border-stone-200 flex items-center justify-between">
          <h2 className="font-mono text-xs uppercase tracking-wider text-stone-700">
            {spawnedId ? "Child investigation" : "Chase this"}
          </h2>
          <button
            onClick={onClose}
            className="text-stone-400 hover:text-stone-900 text-lg leading-none"
            aria-label="Close"
          >
            ×
          </button>
        </header>

        {!spawnedId && (
          <div className="flex-1 flex flex-col p-5 gap-4 overflow-y-auto">
            <div>
              <label className="text-[10px] font-mono uppercase tracking-wider text-stone-500 block mb-1.5">
                Highlighted from parent
              </label>
              <blockquote className="text-sm text-stone-600 italic font-serif border-l-2 border-stone-300 pl-3 py-1">
                "{spawnContext}"
              </blockquote>
            </div>
            <div className="flex-1 flex flex-col">
              <label className="text-[10px] font-mono uppercase tracking-wider text-stone-500 block mb-1.5">
                Question to chase
              </label>
              <textarea
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                rows={6}
                disabled={busy}
                autoFocus
                className="flex-1 border border-stone-300 rounded-md px-3 py-2 text-sm font-serif leading-relaxed focus:outline-none focus:ring-2 focus:ring-stone-900/10 focus:border-stone-400 disabled:opacity-50 resize-none"
              />
            </div>
            {error && (
              <div className="text-xs font-mono text-red-700">{error}</div>
            )}
            <div className="flex items-center justify-end gap-2">
              <button
                onClick={onClose}
                disabled={busy}
                className="px-3 py-1.5 text-sm text-stone-600 hover:text-stone-900 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() => void spawn()}
                disabled={busy || question.trim().length < 3}
                className="px-4 py-1.5 bg-stone-900 text-white text-sm rounded-md hover:bg-stone-700 disabled:bg-stone-400 transition-colors"
              >
                {busy ? "Spawning…" : "Spawn investigation"}
              </button>
            </div>
          </div>
        )}

        {spawnedId && (
          <SpawnedTrajectory
            childId={spawnedId}
            onOpenInMain={() => {
              onClose();
              navigate(`/inv/${spawnedId}`);
            }}
          />
        )}
      </div>
    </div>
  );
}

function SpawnedTrajectory({
  childId,
  onOpenInMain,
}: {
  childId: string;
  onOpenInMain: () => void;
}) {
  const inv = useInvestigation(childId);
  return (
    <div className="flex-1 flex flex-col min-h-0">
      <div className="px-5 py-2 border-b border-stone-200 flex items-center justify-between text-xs">
        <span className="font-mono text-stone-500">{childId}</span>
        <button
          onClick={onOpenInMain}
          className="font-mono text-stone-700 hover:text-stone-900 transition-colors"
        >
          open in main view →
        </button>
      </div>
      <div className="flex-1 min-h-0 overflow-hidden">
        <TrajectoryView investigation={inv} />
      </div>
    </div>
  );
}
