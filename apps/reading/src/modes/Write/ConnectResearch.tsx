import { useEffect, useState } from "react";

import ModelUsagePicker from "../../components/ai/ModelUsagePicker";
import { useOwnerModelChoice } from "../../hooks/useOwnerModelChoice";
import {
  listInvestigations,
  startInvestigation,
  type InvestigationSummary,
} from "../../lib/api";

/**
 * ConnectResearch — the M1 connect step (Write SPR-09).
 *
 * Starting a piece prompts which research project it connects to. The operator
 * weighed merging Write into Research and chose AGAINST it ("writing has
 * sanctity"; "not all writing needs research"). So Write stays net-new — but
 * every piece is BACKED by a research folder. This component is that bridge:
 *
 *   • pick a project → the piece links to it (deliverables.investigation_root_id);
 *     its insight/question blocks import onto the SPR-03 Canvas (the host
 *     mounts the imported Canvas; we do not re-implement one).
 *   • pick "none"   → we AUTO-SPAWN a research folder (startInvestigation) and
 *     link the piece to it, so a piece is never an island over the ONE graph.
 *
 * The link is the SHIPPED `investigation_root_id` (1:1; see
 * docs/decisions/spr-09-write-canvas-xray-rewrite.md, D-1) — not a new column.
 *
 * This component does NOT create the deliverable. It resolves the chosen
 * `investigation_root_id` (existing or freshly spawned) and hands it back; the
 * host (WriteHome) creates the piece with that id, so the link is set at
 * creation and is read back from the substrate (verified by the link existing,
 * not by a UI claim).
 */

export interface ConnectResearchProps {
  /** Resolve the connection: the chosen/spawned investigation id + a label for
   * the header. The host then creates the deliverable with this root id. */
  onConnect: (resolved: { investigationId: string; label: string }) => void;
  /** The piece's title — seeds the auto-spawned research question so the folder
   * isn't a blank "Untitled". */
  pieceTitle: string;
  disabled?: boolean;
  /** From AutoNotebook `/write?investigation=` — same connectExisting path. */
  preferredInvestigationId?: string | null;
}

export default function ConnectResearch({
  onConnect,
  pieceTitle,
  disabled,
  preferredInvestigationId,
}: ConnectResearchProps) {
  const [projects, setProjects] = useState<InvestigationSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [spawning, setSpawning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // The auto-spawned folder is a real research launch — it spends. So the
  // writer picks the route that runs it, the same control the research home
  // offers. The spawn carries no parent and no chased passage, which is what
  // the server requires before it will honour an owner-chosen route.
  const model = useOwnerModelChoice("connect");

  useEffect(() => {
    let cancelled = false;
    listInvestigations({ limit: 50 })
      .then((r) => {
        if (!cancelled) setProjects(r.investigations);
      })
      .catch(() => {
        // A failed list is shown plainly — the writer can still start fresh.
        if (!cancelled) setError("Couldn't load your research projects.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function connectExisting(p: InvestigationSummary) {
    if (disabled) return;
    onConnect({
      investigationId: p.investigation_id,
      label: p.question?.trim() || "a research project",
    });
  }

  async function connectNone() {
    if (disabled || spawning) return;
    setSpawning(true);
    setError(null);
    try {
      // Auto-spawn the backing research folder. The piece title seeds the
      // question so the folder is legible, not "Untitled". This is the bridge,
      // not a merge — the writing canvas/outline/X-ray remain Write's own.
      const spawned = await startInvestigation({
        question: pieceTitle.trim() || "Untitled piece",
        context: "Auto-spawned research folder backing a Write piece (SPR-09 M1).",
        ...model.launchFields(pieceTitle.trim() || "Untitled piece"),
      });
      onConnect({
        investigationId: spawned.investigation_id,
        label: "a new research folder",
      });
    } catch (e) {
      setError(
        e instanceof Error
          ? `Couldn't start a research folder: ${e.message}`
          : "Couldn't start a research folder.",
      );
    } finally {
      setSpawning(false);
    }
  }

  return (
    <div data-testid="connect-research" className="space-y-3">
      <div>
        <h2 className="text-sm font-semibold text-ink dark:text-bright">
          Connect this piece to research
        </h2>
        <p className="mt-0.5 text-xs text-ink-mute dark:text-moonlight">
          Pick a project to pull its insights and open questions onto your
          canvas — or start without one and we'll open a fresh research folder
          to back it.
        </p>
      </div>

      {error && (
        <p className="text-xs text-emperor" role="alert">
          {error}
        </p>
      )}

      <div className="flex items-center gap-2">
        <span className="text-[10px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
          Model for the backing research
        </span>
        <ModelUsagePicker
          models={model.models}
          value={model.selectedRowId}
          onChange={model.select}
          includeDefault
          defaultLabel="Default (house route)"
          triggerLabel={model.triggerLabel}
          triggerAriaLabel="Model for the backing research"
          size="sm"
        />
        {model.state === "error" && (
          <span className="text-[10px] font-mono text-emperor" aria-live="polite">
            Your models couldn’t load. Default is still available.
          </span>
        )}
      </div>

      <button
        type="button"
        onClick={() => void connectNone()}
        disabled={disabled || spawning}
        className="w-full rounded border border-dashed border-rule px-3 py-2 text-left text-sm hover:border-sun-deep disabled:opacity-60 dark:border-charcoal-1"
      >
        <span className="font-medium text-ink dark:text-bright">
          {spawning ? "Opening a research folder…" : "Start without a project"}
        </span>
        <span className="block text-[11px] text-ink-mute dark:text-moonlight">
          We'll auto-spawn a backing research folder and link it.
        </span>
      </button>

      {loading ? (
        <p className="text-xs italic text-ink-mute dark:text-moonlight">
          Loading your research projects…
        </p>
      ) : projects.length > 0 ? (
        <>
          {preferredInvestigationId ? (
            <p
              className="text-xs text-aurora"
              data-testid="connect-research-preferred"
            >
              Pre-selected from your notebook — connect to import the research
              outline into Write when a synthesis exists (else an empty linked
              piece). Daily loop: research → notebook → write.
            </p>
          ) : null}
          <ul className="max-h-56 space-y-1 overflow-y-auto">
          {([...projects].sort((a, b) => {
              const pref = preferredInvestigationId ?? "";
              if (!pref) return 0;
              if (a.investigation_id === pref) return -1;
              if (b.investigation_id === pref) return 1;
              return 0;
            })).map((p) => (
            <li key={p.investigation_id}>
              <button
                type="button"
                onClick={() => void connectExisting(p)}
                disabled={disabled || spawning}
                className={`w-full rounded border px-3 py-2 text-left hover:border-sun-deep disabled:opacity-60 dark:bg-charcoal-2 ${preferredInvestigationId === p.investigation_id ? "border-aurora bg-ice-1 dark:border-aurora" : "border-rule bg-ice-0 dark:border-charcoal-1"}`}
              >
                <span className="block truncate font-serif text-sm text-ink dark:text-bright">
                  {p.question?.trim() || "(untitled research)"}
                </span>
                <span className="text-[10px] uppercase tracking-wide text-ink-mute dark:text-moonlight">
                  {p.status}
                  {p.spawned_by_daemon ? " · found by the loop" : ""}
                </span>
              </button>
            </li>
          ))}
        </ul>
        </>

      ) : (
        <p className="text-xs italic text-ink-mute dark:text-moonlight">
          No research projects yet — start without one and we'll open a folder.
        </p>
      )}
    </div>
  );
}
