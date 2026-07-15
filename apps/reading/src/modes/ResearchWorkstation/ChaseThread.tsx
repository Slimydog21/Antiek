import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import LemonButton from "../../components/lemon/LemonButton";
import LemonTextarea from "../../components/lemon/LemonTextarea";
import { useInvestigation } from "../../hooks/useInvestigation";
import { recordSpawnRelationship } from "../../hooks/useInvestigationTree";
import { startInvestigation, ApiError } from "../../lib/api";
import AIActionFailure from "../../shared/AIActionFailure";
import { CelebrateBurst, useCelebrate } from "../../shared/delight";
import { useWorkspace } from "../../workspace/WorkspaceStore";
import ThinkingStream from "./ThinkingStream";
import VoiceChaseButton from "./VoiceChaseButton";
import type { SelectionProvenance } from "../shared/FloatMenu/useFloatMenuSelection";

/**
 * ChaseThread — follow a highlighted passage into a child research, in one
 * gesture (SPR-04 M2). The delightful, jargon-free successor to
 * ChaseSlideOver: the reader highlights a passage, refines the question if
 * they like, and clicks "Follow this" — a child research launches and the
 * panel transitions to its live thinking stream.
 *
 * Three properties make this hard-to-vary, not just a renamed button:
 *
 * 1. **Reuse the reserved escalation id.** SPR-03's living-note escalation
 *    mints a RESERVED (un-launched) child research id on a question it
 *    can't resolve (``question.escalated_to_research`` →
 *    ``reserved_child_investigation_id``; see
 *    ``roles/note_taker/living_note.py:180``). When the chased passage IS
 *    that escalated question, we launch INTO the reserved id (pass it as
 *    ``investigation_id``) rather than minting a rogue second child — so an
 *    escalation is never orphaned and there is one research per question,
 *    not two. When the passage has no reserved id (a raw highlight), we
 *    omit ``investigation_id`` and the substrate mints a fresh child
 *    parented to the current research (``app.py:1406`` —
 *    ``req.investigation_id or f"inv-{uuid…}"``). Either way it is the
 *    SAME launch path SPR-01 / ChaseSlideOver use — one launch path, not
 *    two.
 *
 * 2. **One explicit gesture, no auto-spawn.** A launch happens only on the
 *    reader's click. Mounting the panel reserves nothing and launches
 *    nothing; this is consistent with SPR-01's approve-gate and the §16
 *    fan-out discipline (a research is an explicit, costed act).
 *
 * 3. **No substrate vocabulary.** "Follow this", not "Spawn". The reserved
 *    id is consumed silently — never rendered as a label (the user never
 *    sees an ``inv-…`` id). A Werner beat fires once on launch (consumes
 *    the wired-in pose via ``useCelebrate`` — it does not author it).
 *
 * Honest no-key (M4): launching emits the start event regardless of
 * provider keys, but the child research can only THINK with a provider. If
 * the launch call itself fails (e.g. a 503 from the substrate), we show the
 * shared ``AIActionFailure`` — never a fabricated child.
 */
type Props = {
  /** The highlighted passage that seeds the child research's question. */
  spawnContext: string;
  /** The research the chase descends from (the new child's parent). */
  parentInvestigationId: string;
  /**
   * SPR-03's reserved escalation child id, when the chased passage maps to
   * an escalated question. Present ⇒ launch INTO this id (no orphan);
   * absent ⇒ mint a fresh child. The panel never renders it.
   */
  reservedChildId?: string | null;
  /** Exact source identity for revisioned derived HTML selections. */
  sourceProvenance?: SelectionProvenance;
};

export default function ChaseThread({
  spawnContext,
  parentInvestigationId,
  reservedChildId,
  sourceProvenance,
}: Props) {
  const [question, setQuestion] = useState(spawnContext);
  const [busy, setBusy] = useState(false);
  const [launchedId, setLaunchedId] = useState<string | null>(null);
  const [error, setError] = useState<{ reason: string | null } | null>(null);
  const navigate = useNavigate();
  const { celebrating, celebrate } = useCelebrate();

  // Reopened with a new selection → reset the form.
  useEffect(() => {
    setQuestion(spawnContext);
    setLaunchedId(null);
    setError(null);
  }, [spawnContext]);

  async function follow() {
    const q = question.trim();
    if (q.length < 3) {
      setError({ reason: "There’s nothing here to follow yet." });
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const derivedSource = /^ast_[0-9a-f]{32}$/.test(sourceProvenance?.documentId ?? "")
        && /^rev_[0-9a-f]{32}$/.test(sourceProvenance?.derivedRevisionId ?? "")
        && /^[0-9a-f]{64}$/.test(sourceProvenance?.derivedContentSha256 ?? "")
        && Number.isInteger(sourceProvenance?.derivedGeneration)
        && (sourceProvenance?.derivedGeneration ?? 0) >= 1
        ? {
            derived_asset_id: sourceProvenance?.documentId,
            revision_id: sourceProvenance?.derivedRevisionId,
            content_sha256: sourceProvenance?.derivedContentSha256,
            generation: sourceProvenance?.derivedGeneration,
          }
        : null;
      const resp = await startInvestigation({
        question: q,
        context: derivedSource
          ? `${spawnContext}\n\nAntiek source identity: ${JSON.stringify(derivedSource)}`
          : spawnContext,
        parent_investigation_id: parentInvestigationId,
        spawn_context: spawnContext,
        // Consume the reserved escalation id when the passage carries one;
        // omit it otherwise so the substrate mints a fresh child. This is
        // the no-orphan / one-research-per-question seam.
        ...(reservedChildId ? { investigation_id: reservedChildId } : {}),
      });
      setLaunchedId(resp.investigation_id);
      recordSpawnRelationship(resp.investigation_id, parentInvestigationId);
      // The payoff is already in hand (the id is back); the beat just
      // decorates it — non-blocking, fires once.
      celebrate();
    } catch (e) {
      const reason = e instanceof ApiError ? e.body || null : null;
      setError({ reason });
    } finally {
      setBusy(false);
    }
  }

  const onFollow = () => {
    void follow();
  };

  if (launchedId) {
    return (
      <LaunchedThread
        childId={launchedId}
        onOpenInMain={() => navigate(`/inv/${launchedId}`)}
      />
    );
  }

  return (
    <div className="flex flex-col p-4 gap-4 h-full text-ink dark:text-bright">
      <div>
        <label className="text-[10px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight block mb-1.5">
          Following from this passage
        </label>
        <blockquote className="text-sm font-serif text-ink-soft dark:text-starlight italic border-l-edge border-sun pl-3 py-1 leading-relaxed">
          “{spawnContext}”
        </blockquote>
      </div>

      <div className="flex-1 flex flex-col min-h-0">
        <label className="text-[10px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight block mb-1.5">
          What do you want to find out?
        </label>
        <LemonTextarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          disabled={busy}
          autoFocus
          minRows={5}
          maxRows={12}
          onSubmit={onFollow}
          className="font-serif"
        />
        <div className="mt-2">
          {/* M4: a voice note can drive the chase — transcribe → set the
              question. Reuses the shipped voice capture; honest no-key
              lives in the transcribe path. */}
          <VoiceChaseButton
            disabled={busy}
            onTranscript={(t) => setQuestion(t)}
          />
        </div>
      </div>

      {error && (
        <AIActionFailure
          title="Couldn’t follow this thread"
          reason={error.reason}
          onRetry={onFollow}
          retryLabel="Try again"
        />
      )}

      <div className="flex items-center justify-end gap-2">
        <CelebrateBurst active={celebrating} size={40} />
        <LemonButton
          variant="primary"
          onClick={onFollow}
          disabled={busy || question.trim().length < 3}
        >
          {busy ? "Following…" : "Follow this"}
        </LemonButton>
      </div>
    </div>
  );
}

/** The launched child research's live thinking stream, in-panel. The user
 *  can pop it into the main view. Mirrors ChaseSlideOver's SpawnedTrajectory
 *  but without the "spawn" vocabulary. */
function LaunchedThread({
  childId,
  onOpenInMain,
}: {
  childId: string;
  onOpenInMain: () => void;
}) {
  const inv = useInvestigation(childId);
  const getState = useWorkspace.getState;
  return (
    <div className="flex flex-col h-full text-ink dark:text-bright">
      <div className="px-3 py-2 border-b border-rule dark:border-charcoal-1 flex items-center justify-between text-xs font-mono">
        <span className="text-shadow-1 dark:text-moonlight">following the thread…</span>
        <button
          type="button"
          onClick={() => {
            onOpenInMain();
            // Close THIS chase panel after navigating away.
            const ws = getState();
            const me = Object.values(ws.panels).find(
              (p) =>
                p.kind === "ChaseThread" &&
                (p.props as { parentInvestigationId?: string }).parentInvestigationId,
            );
            if (me) getState().close(me.id);
          }}
          className="text-ink dark:text-bright hover:underline shrink-0 ml-2"
        >
          open in main view →
        </button>
      </div>
      <div className="flex-1 min-h-0 overflow-hidden">
        {/* The child IS a running research — narrate it (SPR-02), raw log
            one toggle away inside ThinkingStream. */}
        <ThinkingStream investigation={inv} />
      </div>
    </div>
  );
}
