import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import {
  createDeliverable,
  getDeliverable,
  listDeliverables,
  type DeliverableDetailResponse,
  type DeliverableKind,
  type DeliverableSummary,
} from "../../lib/api";
import BlockRepository from "./BlockRepository";
import { ContextWindow } from "./ContextWindow/ContextWindow";
import { IdeaDump } from "./Brainstorm/IdeaDump";
import Outline from "./Outline";
import { onTraceIntent } from "./Editor/traceIntent";
import { getTraceTarget, type RepositoryHit } from "./writeApi";

/**
 * Write Home — the Write door (Product Depth SPR-07 M1).
 *
 * Replaces the legacy CreationStudio dead-end ("Select or create a deliverable
 * to begin.") as the surface the Write rail opens. It teaches the whole loop
 * in one screen: a piece on the left as a legible outline, your block
 * repository on the right as a search-first TAP-to-add picker, one obvious
 * "Generate draft" per section, the real editor where the draft lands, and a
 * brainstorm on-ramp for starting from a raw idea instead of an outline.
 *
 * The create-deliverable button itself is hotfixed on `fix/lived-bugs`; this
 * surface owns the loop BEHIND it — once a piece exists (or you start one
 * here), the blocks→outline→generate→edit flow lives here.
 *
 * Routing: `/write` lands here with no piece (start one or brainstorm);
 * `/write/:deliverableId` opens onto that piece's outline. No id is ever
 * shown — the piece is named by its title, blocks by their text + provenance.
 */
export default function WriteHome() {
  const { deliverableId } = useParams<{ deliverableId?: string }>();
  const navigate = useNavigate();

  const [detail, setDetail] = useState<DeliverableDetailResponse | null>(null);
  const [pieces, setPieces] = useState<DeliverableSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [onRamp, setOnRamp] = useState<"idea" | "context" | null>(null);

  // The active tap-to-add handler, registered by the Outline (binds the tap to
  // the active section). A ref so re-registers don't re-render the repository.
  const addHandler = useRef<(hit: RepositoryHit) => void>(() => {});
  const registerAddHandler = useCallback((h: (hit: RepositoryHit) => void) => {
    addHandler.current = h;
  }, []);

  const refresh = useCallback(async () => {
    if (!deliverableId) {
      setDetail(null);
      return;
    }
    setLoading(true);
    try {
      setDetail(await getDeliverable(deliverableId));
    } catch {
      setDetail(null);
    } finally {
      setLoading(false);
    }
  }, [deliverableId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (deliverableId) return; // only list pieces on the home (no piece) view
    listDeliverables()
      .then((r) => setPieces(r.deliverables))
      .catch(() => setPieces([]));
  }, [deliverableId]);

  // Trace-to-source (M4): when a citation chip in the editor is clicked it
  // emits a decoupled intent (Editor/traceIntent.ts). The shared reader (DRW
  // SPR-10) is still unbuilt, so we resolve the trace target and route to the
  // book reader when the source is servable — with an honest fallback when it
  // isn't reachable (gated source, no reader), never a broken trip.
  useEffect(() => {
    return onTraceIntent((intent) => {
      if (!intent.outlineBlockId) {
        window.alert("This is your own note — it traces to your session, not an external source.");
        return;
      }
      void (async () => {
        try {
          const target = await getTraceTarget(intent.outlineBlockId!);
          if (target.full_text_allowed && target.document_id) {
            navigate(`/read/${encodeURIComponent(target.document_id)}`);
          } else {
            // Honest fallback (§9.0): gated/unreachable source — say so, don't
            // open a dead page.
            window.alert(
              target.detail ??
                "That source isn't available to open here — it's gated or not reachable yet.",
            );
          }
        } catch {
          window.alert("Couldn't reach that source right now. Try again.");
        }
      })();
    });
  }, [navigate]);

  // The "start a piece" action — the obvious way to begin (WX-01). The create
  // button bug is fixed elsewhere; this is the working path into the loop.
  const [starting, setStarting] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const [newKind, setNewKind] = useState<DeliverableKind>("general_essay");

  async function startPiece(e: React.FormEvent) {
    e.preventDefault();
    if (!newTitle.trim()) return;
    setStarting(true);
    try {
      const d = await createDeliverable({
        title: newTitle.trim(),
        deliverable_kind: newKind,
      });
      navigate(`/write/${d.deliverable_id}`);
    } finally {
      setStarting(false);
    }
  }

  // ── Home (no piece selected): start one, pick one, or brainstorm. ──
  if (!deliverableId) {
    return (
      <div className="mx-auto h-full max-w-3xl overflow-y-auto px-6 py-8">
        <header className="mb-6">
          <h1 className="font-serif text-2xl font-semibold text-ink dark:text-bright">
            Write a piece
          </h1>
          <p className="mt-1 text-sm text-ink-soft dark:text-moonlight">
            Pull your research notes into an outline, generate a first draft
            from them, then edit. Or dump a raw idea and let the blocks fall out.
          </p>
        </header>

        <form
          onSubmit={startPiece}
          className="mb-6 flex flex-wrap items-center gap-2 rounded-md border border-rule bg-ice-0 p-3 dark:border-charcoal-1 dark:bg-charcoal-2"
        >
          <input
            value={newTitle}
            onChange={(e) => setNewTitle(e.target.value)}
            placeholder="What are you writing? (a title)"
            className="min-w-[220px] flex-1 rounded border border-rule px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-sun dark:border-charcoal-1"
          />
          <select
            value={newKind}
            onChange={(e) => setNewKind(e.target.value as DeliverableKind)}
            className="rounded border border-rule px-2 py-2 text-xs focus:outline-none focus:ring-2 focus:ring-sun dark:border-charcoal-1"
          >
            <option value="general_essay">Essay</option>
            <option value="research_memo">Research memo</option>
            <option value="book_chapter">Book chapter</option>
            <option value="biography_section">Biography section</option>
            <option value="investor_brief">Investor brief</option>
          </select>
          <button
            type="submit"
            disabled={starting || !newTitle.trim()}
            className="rounded bg-ink px-4 py-2 text-sm font-medium text-white hover:bg-shadow-2 disabled:bg-glacial-1 dark:disabled:bg-slate-1"
          >
            {starting ? "Starting…" : "Start writing"}
          </button>
          <button
            type="button"
            onClick={() => setOnRamp((v) => (v === "idea" ? null : "idea"))}
            className="text-sm text-ink-soft underline hover:text-ink dark:text-starlight"
          >
            or brainstorm from an idea
          </button>
        </form>

        {onRamp === "idea" && (
          <div className="mb-6 rounded-md border border-rule dark:border-charcoal-1">
            <p className="px-4 pt-3 text-xs text-ink-mute dark:text-moonlight">
              Think aloud here. The drivers you confirm become blocks you can
              outline and draft from — start a piece first to land them on it.
            </p>
            <IdeaDump sectionId="__brainstorm__" />
          </div>
        )}

        {pieces.length > 0 && (
          <section>
            <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-mute dark:text-moonlight">
              Your pieces
            </h2>
            <ul className="space-y-1">
              {pieces.map((p) => (
                <li key={p.deliverable_id}>
                  <button
                    type="button"
                    onClick={() => navigate(`/write/${p.deliverable_id}`)}
                    className="w-full rounded border border-rule bg-ice-0 px-3 py-2 text-left hover:border-ocean dark:border-charcoal-1 dark:bg-charcoal-2"
                  >
                    <span className="font-serif text-ink dark:text-bright">{p.title}</span>
                    <span className="ml-2 text-xs text-ink-mute dark:text-moonlight">
                      {p.section_count} section{p.section_count === 1 ? "" : "s"}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>
    );
  }

  // ── A piece is open: the outline + repository loop. ──
  return (
    <div className="flex h-full min-h-0 bg-ice-1 dark:bg-charcoal-2">
      <main className="flex min-w-0 flex-1 flex-col px-6 py-5">
        <header className="mb-4 flex items-baseline justify-between gap-3">
          <div className="min-w-0">
            <button
              type="button"
              onClick={() => navigate("/write")}
              className="text-xs text-ink-soft underline hover:text-ink dark:text-starlight"
            >
              ← all pieces
            </button>
            <h1 className="truncate font-serif text-xl font-semibold text-ink dark:text-bright">
              {detail?.title ?? (loading ? "Opening…" : "Piece")}
            </h1>
          </div>
          <button
            type="button"
            onClick={() => setOnRamp((v) => (v === "context" ? null : "context"))}
            className="shrink-0 text-xs text-ink-soft underline hover:text-ink dark:text-starlight"
          >
            {onRamp === "context" ? "hide brainstorm" : "brainstorm a section"}
          </button>
        </header>

        {onRamp === "context" && (
          <div className="mb-4 rounded-md border border-rule dark:border-charcoal-1">
            <p className="px-4 pt-3 text-xs text-ink-mute dark:text-moonlight">
              The outline-optional path: drop blocks and state an objective,
              then generate directly. No fabricated sources — blocks first.
            </p>
            <ContextWindow />
          </div>
        )}

        {detail ? (
          <Outline
            deliverableId={detail.deliverable_id}
            sections={detail.sections}
            onChanged={refresh}
            registerAddHandler={registerAddHandler}
          />
        ) : (
          <p className="font-serif text-sm italic text-ink-mute dark:text-moonlight">
            {loading ? "Opening the piece…" : "That piece isn't available."}
          </p>
        )}
      </main>

      <aside className="hidden w-80 shrink-0 flex-col border-l border-rule bg-ice-0 p-4 dark:border-charcoal-1 dark:bg-charcoal-2 lg:flex">
        <BlockRepository onAdd={(hit) => addHandler.current(hit)} />
      </aside>
    </div>
  );
}
