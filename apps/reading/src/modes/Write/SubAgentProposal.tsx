import { useEffect, useState } from "react";

// Collective multi-agent merge invent — sub-agent spin is the product door for
// merging floating research instances into a cohesive strengthen pass.
import collectiveMergeArt from "../../brand/werner/poses/session/werner_collective_merge_session_v1.webp";
import "../../brand/sessionLivingTv.css";
import { startInvestigation } from "../../lib/api";
import AIActionFailure from "../../shared/AIActionFailure";
import Thinking from "../../shared/Thinking";
import { emitWernerExperience } from "../../werner/reactionBus";
import { searchRepository, type RepositoryHit } from "./writeApi";

/**
 * SubAgentProposal — "spin a sub-agent to search + strengthen" (Write SPR-09 M4).
 *
 * The third FloatMenu rewrite action. It launches a SEARCH over the highlighted
 * claim and returns an accept/reject PROPOSAL: the strongest corroborating
 * blocks found, plus the option to spin a full child investigation to chase the
 * claim. ACCEPT spawns the child research (the SHIPPED `startInvestigation`
 * spawn path — no new spawn path); REJECT discards. Nothing is committed until
 * the writer accepts (a proposal, not an auto-edit).
 *
 * §9.0: the host already routed the selection through `outboundText` — a
 * withheld selection arrives as `null` and we never reach here (the host
 * refuses). The text we search/spawn on is the §9.0-safe text.
 *
 * Honest about no-key: a spawn that 503s surfaces AIActionFailure (the spawn
 * couldn't run), never a fabricated "strengthened" claim.
 */

export interface SubAgentProposalProps {
  /** The §9.0-safe highlighted text to strengthen (never null here — the host
   * refuses a withheld selection before opening this). */
  claimText: string;
  /** The piece's backing research folder — the child investigation's parent. */
  parentInvestigationId: string;
  onAccept: (childInvestigationId: string) => void;
  onReject: () => void;
}

export default function SubAgentProposal({
  claimText,
  parentInvestigationId,
  onAccept,
  onReject,
}: SubAgentProposalProps) {
  const [hits, setHits] = useState<RepositoryHit[] | null>(null);
  const [searching, setSearching] = useState(true);
  const [spawning, setSpawning] = useState(false);
  const [failure, setFailure] = useState<{ reason: string | null } | null>(null);

  // Launch the search over the claim (the "search" half of search+strengthen).
  useEffect(() => {
    let cancelled = false;
    setSearching(true);
    searchRepository({ q: claimText, limit: 5 })
      .then((h) => {
        if (!cancelled) setHits(h);
      })
      .catch(() => {
        if (!cancelled) setHits([]);
      })
      .finally(() => {
        if (!cancelled) setSearching(false);
      });
    return () => {
      cancelled = true;
    };
  }, [claimText]);

  async function accept() {
    setSpawning(true);
    setFailure(null);
    // Living-TV: accept spins a sub-agent deep research.
    emitWernerExperience("deep_research_start");
    try {
      // The SHIPPED spawn path — a child investigation chasing the claim,
      // parented to the piece's backing folder. No new spawn path.
      const child = await startInvestigation({
        question: `Strengthen: ${claimText}`,
        spawn_context: claimText,
        parent_investigation_id: parentInvestigationId,
      });
      onAccept(child.investigation_id);
    } catch (e) {
      emitWernerExperience("deep_research_error");
      const status = (e as { status?: number })?.status;
      setFailure({ reason: status === 503 ? null : e instanceof Error ? e.message : String(e) });
    } finally {
      setSpawning(false);
    }
  }

  return (
    <div
      data-testid="sub-agent-proposal"
      className="rounded-md border border-ocean/50 bg-ocean/5 p-3 text-sm"
    >
      {/* Living-TV invent — collective multi-agent merge product door. */}
      <img
        src={collectiveMergeArt}
        alt=""
        aria-hidden="true"
        data-testid="sub-agent-proposal-living-tv-art"
        className="mb-2 h-10 w-full max-w-xs rounded object-cover object-center antiek-living-tv-invent"
        loading="lazy"
        decoding="async"
      />
      <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-ocean">
        Strengthen this claim
      </p>
      <blockquote className="mb-2 border-l-2 border-sun pl-2 text-[13px] italic text-ink dark:text-bright line-clamp-2">
        "{claimText}"
      </blockquote>

      {failure ? (
        <AIActionFailure
          title="The sub-agent couldn't run"
          reason={failure.reason}
          onRetry={() => setFailure(null)}
        />
      ) : searching ? (
        <Thinking size={22} status="searching the corpus…" />
      ) : (
        <>
          {hits && hits.length > 0 ? (
            <ul className="mb-2 space-y-1">
              {hits.map((h) => (
                <li key={h.node_id} className="text-[12px] text-ink dark:text-bright">
                  <span className="text-ink-mute dark:text-moonlight">
                    {h.document_title ?? "your note"}
                  </span>{" "}
                  · {h.label}
                </li>
              ))}
            </ul>
          ) : (
            <p className="mb-2 text-[12px] italic text-ink-mute dark:text-moonlight">
              Nothing in the corpus yet — spin a sub-agent to go find support.
            </p>
          )}
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => void accept()}
              disabled={spawning}
              className="rounded bg-ink px-3 py-1.5 text-xs text-white hover:bg-shadow-2 disabled:bg-glacial-1 dark:disabled:bg-slate-1"
            >
              {spawning ? "Spinning…" : "Accept — spin a sub-agent"}
            </button>
            <button
              type="button"
              onClick={() => {
                emitWernerExperience("highlight");
                onReject();
              }}
              disabled={spawning}
              className="text-xs text-ink-soft underline hover:text-ink dark:text-starlight"
            >
              Reject
            </button>
          </div>
        </>
      )}
    </div>
  );
}
