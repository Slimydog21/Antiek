import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import LemonButton from "../../components/lemon/LemonButton";
import LemonTextarea from "../../components/lemon/LemonTextarea";
import { useInvestigation } from "../../hooks/useInvestigation";
import { recordSpawnRelationship } from "../../hooks/useInvestigationTree";
import { startInvestigation } from "../../lib/api";
import { useWorkspace } from "../../workspace/WorkspaceStore";
import { emitWernerExperience } from "../../werner/reactionBus";
import ThinkingStream from "./ThinkingStream";

/**
 * Chase-this flow — pre-fills a textarea with a highlighted passage,
 * lets the operator refine it, spawns a child investigation, then
 * transitions to the child's live trajectory.
 *
 * S5 conversion: this is now a workspace floating PANEL (PanelKind = "Chase"),
 * not a controlled slide-over. The operator opens it via
 *
 *   useWorkspace.getState().open("Chase",
 *     { spawnContext, parentInvestigationId },
 *     { mode: "floating", title: "Chase" })
 *
 * and the panel reads its props from the workspace descriptor.
 * Dismissal goes through the panel's normal close action — no
 * `open` / `onClose` props from the parent.
 */
type Props = {
  spawnContext: string;
  parentInvestigationId: string;
};

export default function ChaseSlideOver({ spawnContext, parentInvestigationId }: Props) {
  const [question, setQuestion] = useState(spawnContext);
  const [busy, setBusy] = useState(false);
  const [spawnedId, setSpawnedId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  // If the spawnContext changes mid-life (operator reopens with a new
  // selection), reset the form.
  useEffect(() => {
    setQuestion(spawnContext);
    setSpawnedId(null);
    setError(null);
  }, [spawnContext]);

  async function spawn() {
    const q = question.trim();
    if (q.length < 3) {
      setError("Question is too short.");
      return;
    }
    setBusy(true);
    setError(null);
    // Living-TV: chase spawn is a deep-research start from a highlight.
    emitWernerExperience("deep_research_start");
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
      emitWernerExperience("deep_research_error");
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  if (spawnedId) {
    return (
      <SpawnedTrajectory
        childId={spawnedId}
        onOpenInMain={() => navigate(`/inv/${spawnedId}`)}
      />
    );
  }

  return (
    <div className="flex flex-col p-4 gap-4 h-full text-ink dark:text-bright">
      <div>
        <label className="text-[10px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight block mb-1.5">
          Highlighted from parent
        </label>
        <blockquote className="text-sm font-serif text-ink-soft dark:text-starlight italic border-l-edge border-sun pl-3 py-1 leading-relaxed">
          "{spawnContext}"
        </blockquote>
      </div>

      <div className="flex-1 flex flex-col min-h-0">
        <label className="text-[10px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight block mb-1.5">
          Question to chase
        </label>
        <LemonTextarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          disabled={busy}
          autoFocus
          minRows={5}
          maxRows={12}
          onSubmit={() => void spawn()}
          className="font-serif"
        />
      </div>

      {error && (
        <div className="text-xs font-mono text-emperor">{error}</div>
      )}

      <div className="flex items-center justify-end gap-2">
        <LemonButton
          variant="primary"
          onClick={() => void spawn()}
          disabled={busy || question.trim().length < 3}
        >
          {busy ? "Spawning…" : "Spawn investigation"}
        </LemonButton>
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
  const close = useWorkspace.getState;
  return (
    <div className="flex flex-col h-full text-ink dark:text-bright">
      <div className="px-3 py-2 border-b border-rule dark:border-charcoal-1 flex items-center justify-between text-xs font-mono">
        <span className="text-shadow-1 dark:text-moonlight truncate">{childId}</span>
        <button
          type="button"
          onClick={() => {
            onOpenInMain();
            // Close THIS chase panel after navigating away — find by props match
            const ws = close();
            const me = Object.values(ws.panels).find(
              (p) => p.kind === "Chase" && (p.props as { parentInvestigationId?: string }).parentInvestigationId,
            );
            if (me) close().close(me.id);
          }}
          className="text-ink dark:text-bright hover:underline shrink-0 ml-2"
        >
          open in main view →
        </button>
      </div>
      <div className="flex-1 min-h-0 overflow-hidden">
        {/* SPR-02: a spawned chase is a running research too — narrate it,
            with the raw log one toggle away (inside ThinkingStream). */}
        <ThinkingStream investigation={inv} />
      </div>
    </div>
  );
}
