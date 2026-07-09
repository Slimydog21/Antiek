import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";

import {
  createDeliverable,
  createSection,
  getDeliverable,
  listDeliverables,
  updateSectionProse,
  type DeliverableDetailResponse,
  type DeliverableKind,
  type DeliverableSummary,
} from "../../lib/api";
import { seedTwinNotes } from "../../api/engagement";
import { fetchHostedDocumentHtml } from "../../api/marketplaceHost";
import GlassSurface from "../../shell/GlassSurface";
import Canvas from "../DeepResearchWorkspace/Canvas/Canvas";
import BlockRepository from "./BlockRepository";
import ConnectResearch from "./ConnectResearch";
import { ContextWindow } from "./ContextWindow/ContextWindow";
import { IdeaDump } from "./Brainstorm/IdeaDump";
import Outline from "./Outline";
import { ProjectTypeField } from "./ProjectType";
import { onTraceIntent } from "./Editor/traceIntent";
import {
  prepareHtmlDraftForWrite,
  type HtmlDraftImportPrepared,
} from "./htmlDraftImport";
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
 *
 * Residual (fl): `?html_draft=<document_id>` handoff from hosted HTML merge.
 * Residual (fm): load hosted HTML, refuse non-html, prefill title + seed
 * brainstorm plain text.
 * Residual (ft): on create piece with loaded HTML draft, create section(s)
 * and PATCH prose (HTML-first land into outline).
 * Residual (fu): multi-section import via h1–h3 split (outline_sections).
 * Residual (fv): nest h2/h3 under preceding higher-level section via
 * parent_section_id when createSection accepts it.
 * Residual (fx): prefer html_fragment for section prose (HTML-first land).
 * Residual (fz): offline twin seed on deliverable after HTML draft import
 * (recursive note-taker substrate for the new writing asset).
 */
export default function WriteHome() {
  const { deliverableId } = useParams<{ deliverableId?: string }>();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  // Residual (fl/fm): HTML draft handoff from reading/research merge flywheel.
  const htmlDraftId = useMemo(
    () => (searchParams.get("html_draft") || "").trim(),
    [searchParams],
  );

  const [detail, setDetail] = useState<DeliverableDetailResponse | null>(null);
  const [pieces, setPieces] = useState<DeliverableSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [onRamp, setOnRamp] = useState<"idea" | "context" | null>(null);
  // Residual (fm): prepared HTML draft for Write surface.
  const [htmlDraft, setHtmlDraft] = useState<HtmlDraftImportPrepared | null>(
    null,
  );
  const [htmlDraftError, setHtmlDraftError] = useState<string | null>(null);
  const [htmlDraftBusy, setHtmlDraftBusy] = useState(false);
  const [brainstormSeed, setBrainstormSeed] = useState<string | null>(null);
  // The "start a piece" action — must be declared before html_draft load effect.
  const [starting, setStarting] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  // Open-ended project type (M4): freeform text the AI interprets; presets seed.
  const [projectType, setProjectType] = useState<{
    freeform: string;
    kind: DeliverableKind;
  }>({ freeform: "", kind: "general_essay" });
  // The piece-view surface: the outline loop, or the imported research canvas
  // (M1 — the SPR-03 Canvas of the linked investigation's blocks).
  const [pieceView, setPieceView] = useState<"outline" | "canvas">("outline");

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

  // Residual (fm): load hosted HTML draft when handoff query is present.
  useEffect(() => {
    if (deliverableId || !htmlDraftId) {
      setHtmlDraft(null);
      setHtmlDraftError(null);
      return;
    }
    let cancelled = false;
    setHtmlDraftBusy(true);
    setHtmlDraftError(null);
    void fetchHostedDocumentHtml(htmlDraftId)
      .then((doc) => {
        if (cancelled) return;
        const prepared = prepareHtmlDraftForWrite({
          document_id: doc.document_id || htmlDraftId,
          view_format: doc.view_format,
          html: doc.html,
          title: doc.title,
        });
        setHtmlDraft(prepared);
        // Prefill piece title when empty so connect-research can proceed.
        setNewTitle((prev) => (prev.trim() ? prev : prepared.title_hint));
        // Residual (fp): stamp project-type freeform with HTML draft provenance.
        setProjectType((prev) =>
          prev.freeform.trim()
            ? prev
            : {
                ...prev,
                freeform: `html_draft:${prepared.document_id}`,
              },
        );
      })
      .catch((e) => {
        if (cancelled) return;
        setHtmlDraft(null);
        setHtmlDraftError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (!cancelled) setHtmlDraftBusy(false);
      });
    return () => {
      cancelled = true;
    };
  }, [deliverableId, htmlDraftId]);

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

  // The "start a piece" action — the obvious way to begin (WX-01). SPR-09 M1:
  // it now runs title → project-type → connect-to-research, so a piece is
  // created WITH its backing investigation_root_id set (the link is set at
  // creation; M1 reads it back to verify it exists).

  async function createWithConnection(resolved: { investigationId: string; label: string }) {
    if (!newTitle.trim()) return;
    setStarting(true);
    try {
      const d = await createDeliverable({
        title: newTitle.trim(),
        // The freeform type resolves to the closest kind (ProjectType.resolveKind);
        // a novel type falls to general_essay — never gated, never crashes.
        deliverable_kind: projectType.kind,
        // M1: the piece↔research link, set at creation (deliverables.
        // investigation_root_id; reused, not a new column — see decision D-1).
        investigation_root_id: resolved.investigationId,
      });
      // Residual (ft/fu/fv): land HTML draft into outline section(s), nested by level.
      // Prefer heading-split outline_sections; fall back to single plain body.
      if (htmlDraft) {
        try {
          const sections =
            htmlDraft.outline_sections?.length > 0
              ? htmlDraft.outline_sections
              : htmlDraft.plain_text?.trim()
                ? [
                    {
                      title: (htmlDraft.title_hint || "Imported HTML draft").slice(
                        0,
                        120,
                      ),
                      plain_text: htmlDraft.plain_text,
                      section_index: 0,
                      heading_level: 0,
                      html_fragment: htmlDraft.html.slice(0, 100_000),
                    },
                  ]
                : [];
          // Residual (fv): track last section id per heading level for nesting.
          const lastIdByLevel: Record<number, string> = {};
          for (const s of sections) {
            if (!s.plain_text?.trim()) continue;
            const level = s.heading_level ?? 0;
            let parent_section_id: string | undefined;
            if (level >= 2) {
              // Prefer parent one level up; walk up if missing.
              for (let p = level - 1; p >= 0; p--) {
                if (lastIdByLevel[p]) {
                  parent_section_id = lastIdByLevel[p];
                  break;
                }
              }
            }
            const sec = await createSection({
              deliverable_id: d.deliverable_id,
              section_index: s.section_index,
              title: (s.title || "Imported section").slice(0, 120),
              ...(parent_section_id
                ? { parent_section_id }
                : {}),
            });
            lastIdByLevel[level] = sec.section_id;
            // Clear deeper levels when we place a shallower heading.
            for (const k of Object.keys(lastIdByLevel)) {
              const kl = Number(k);
              if (kl > level) delete lastIdByLevel[kl];
            }
            // Residual (fx): HTML-first prose when fragment present.
            const prose =
              (s.html_fragment || "").trim() ||
              s.plain_text.slice(0, 100_000);
            await updateSectionProse(sec.section_id, {
              prose_text: prose.slice(0, 100_000),
              promote_to_graph: false,
            });
          }
          // Residual (fz): recursive note-taker twin on the new writing asset.
          try {
            await seedTwinNotes({
              asset_id: d.deliverable_id,
              title: newTitle.trim() || htmlDraft.title_hint,
              body_text: htmlDraft.plain_text.slice(0, 2000),
              include_html: false,
              force_offline: true,
            });
          } catch {
            // Twin seed optional; piece + sections already landed.
          }
        } catch {
          // Non-fatal: piece still opens; operator can paste from brainstorm seed.
        }
      }
      navigate(`/write/${d.deliverable_id}`);
    } finally {
      setStarting(false);
    }
  }

  // ── Home (no piece selected): start one, pick one, or brainstorm. ──
  if (!deliverableId) {
    const htmlDraftBanner = htmlDraftId ? (
      <div
        className="mb-4 space-y-2 rounded border border-ink/20 p-3 font-mono text-[12px] dark:border-bright/20"
        data-testid="write-html-draft-handoff"
        data-view-format="html"
        data-html-draft={htmlDraftId}
        data-load-status={
          htmlDraftBusy ? "loading" : htmlDraftError ? "error" : htmlDraft ? "ready" : "idle"
        }
        role="status"
      >
        <p>
          HTML draft handoff from reading/research: document{" "}
          <code>{htmlDraftId}</code>
          {htmlDraftBusy ? " · loading…" : null}
        </p>
        {htmlDraftError ? (
          <p
            className="text-emperor"
            data-testid="write-html-draft-error"
            role="alert"
          >
            {htmlDraftError}
          </p>
        ) : null}
        {htmlDraft ? (
          <div
            className="space-y-2 border-t border-ink/10 pt-2 dark:border-bright/10"
            data-testid="write-html-draft-loaded"
            data-document-id={htmlDraft.document_id}
          >
            <p data-testid="write-html-draft-title">
              Title: <strong>{htmlDraft.title}</strong>
            </p>
            {/* Residual (fw): preview outline sections that will import on create. */}
            {htmlDraft.outline_sections?.length ? (
              <div
                className="space-y-1"
                data-testid="write-html-draft-section-preview"
                data-section-count={String(htmlDraft.outline_sections.length)}
              >
                <p className="text-[10px] uppercase tracking-wide text-ink-mute dark:text-moonlight">
                  Outline preview (imports on create)
                </p>
                <ol className="list-decimal pl-4 text-[11px]">
                  {htmlDraft.outline_sections.map((s) => (
                    <li
                      key={`${s.section_index}-${s.title}`}
                      data-testid="write-html-draft-section-preview-item"
                      data-heading-level={String(s.heading_level ?? 0)}
                      data-section-index={String(s.section_index)}
                    >
                      <span className="font-semibold">{s.title}</span>
                      {s.heading_level >= 2 ? (
                        <span className="text-ink-mute"> · h{s.heading_level}</span>
                      ) : null}
                      <span className="text-ink-mute">
                        {" "}
                        · {(s.plain_text || "").slice(0, 80)}
                        {(s.plain_text || "").length > 80 ? "…" : ""}
                      </span>
                    </li>
                  ))}
                </ol>
              </div>
            ) : null}
            <p
              className="max-h-24 overflow-auto text-[11px] text-ink-soft dark:text-moonlight"
              data-testid="write-html-draft-plain-preview"
            >
              {htmlDraft.plain_preview}
            </p>
            <div
              className="prose max-h-32 overflow-auto text-sm"
              data-testid="write-html-draft-html-preview"
              dangerouslySetInnerHTML={{
                __html: htmlDraft.html.slice(0, 4000),
              }}
            />
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                data-testid="write-html-draft-use-title"
                className="rounded border border-ink/30 px-2 py-1 text-[11px] hover:bg-ink/5 dark:border-bright/30"
                onClick={() => setNewTitle(htmlDraft.title_hint)}
              >
                Use draft title
              </button>
              <button
                type="button"
                data-testid="write-html-draft-seed-brainstorm"
                className="rounded border border-ink/30 px-2 py-1 text-[11px] hover:bg-ink/5 dark:border-bright/30"
                onClick={() => {
                  setBrainstormSeed(htmlDraft.plain_text.slice(0, 8000));
                  setOnRamp("idea");
                }}
              >
                Seed brainstorm from draft
              </button>
              {/* Residual (ft/fu): import lands on create piece (multi-section). */}
              <span
                className="rounded border border-aurora/40 px-2 py-1 text-[11px] text-aurora"
                data-testid="write-html-draft-import-outline"
                data-import-on-create="true"
                data-html-prose="true"
                data-section-count={String(
                  htmlDraft.outline_sections?.length ?? 0,
                )}
                title="Creating a piece below imports HTML prose into nested outline section(s)"
              >
                Imports on create →{" "}
                {htmlDraft.outline_sections?.length ?? 0} section(s) · HTML
                prose
              </span>
            </div>
            <p
              className="text-[10px] text-ink-mute dark:text-moonlight"
              data-testid="write-html-draft-import-deferred"
            >
              Residual (fu): create a piece below (connect research); h1–h3
              structure becomes outline sections with plain-text prose
              (HTML-first, not PDF). Provenance document{" "}
              <code>{htmlDraft.document_id}</code>.
            </p>
            {/* Residual (fp): visible provenance stamp for freeform project type. */}
            <p
              className="text-[10px] font-mono"
              data-testid="write-html-draft-provenance"
              data-document-id={htmlDraft.document_id}
            >
              Provenance freeform:{" "}
              <code>
                {projectType.freeform.trim() ||
                  `html_draft:${htmlDraft.document_id}`}
              </code>
            </p>
          </div>
        ) : null}
      </div>
    ) : null;

    return (
      // Landing-glass (SPR-03 M2): the Write home is a LANDING surface. The
      // root renders through GlassSurface so the <Scene/> (z-0) shows through;
      // the scrim keeps the heading + the start-a-piece card legible. The card
      // below is glassed too (was an opaque bg-ice-0 dark:bg-charcoal-2 sheet)
      // so the scene reads behind it instead of an ice wall.
      <GlassSurface className="mx-auto h-full max-w-3xl overflow-y-auto px-6 py-8">
        <header className="mb-6">
          <h1 className="font-serif text-2xl font-semibold text-ink dark:text-bright">
            Write a piece
          </h1>
          <p className="mt-1 text-sm text-ink-soft dark:text-moonlight">
            Pull your research notes into an outline, generate a first draft
            from them, then edit. Or dump a raw idea and let the blocks fall out.
          </p>
        </header>

        {htmlDraftBanner}

        <GlassSurface className="mb-6 space-y-3 rounded-md p-3">
          <input
            value={newTitle}
            onChange={(e) => setNewTitle(e.target.value)}
            placeholder="What are you writing? (a title)"
            className="w-full rounded border border-rule px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-sun dark:border-charcoal-1"
          />
          {/* M4: open-ended project type — presets seed, do not gate. */}
          <ProjectTypeField
            value={projectType}
            onChange={setProjectType}
            disabled={starting}
          />
          {/* M1: the connect-to-research step. Pick a project (imports its
              blocks onto the canvas) or none (auto-spawns + links a folder).
              Either way the piece is created WITH investigation_root_id set. */}
          {newTitle.trim() ? (
            <ConnectResearch
              pieceTitle={newTitle}
              disabled={starting}
              onConnect={(resolved) => void createWithConnection(resolved)}
            />
          ) : (
            <p className="text-xs italic text-ink-mute dark:text-moonlight">
              Name the piece to choose a research project to connect it to.
            </p>
          )}
          {starting && (
            <p className="text-xs text-ocean">Starting your piece…</p>
          )}
          <button
            type="button"
            onClick={() => setOnRamp((v) => (v === "idea" ? null : "idea"))}
            className="text-sm text-ink-soft underline hover:text-ink dark:text-starlight"
          >
            or brainstorm from an idea
          </button>
        </GlassSurface>

        {onRamp === "idea" && (
          <div className="mb-6 rounded-md border border-rule dark:border-charcoal-1">
            <p className="px-4 pt-3 text-xs text-ink-mute dark:text-moonlight">
              Think aloud here. The drivers you confirm become blocks you can
              outline and draft from — start a piece first to land them on it.
            </p>
            <IdeaDump
              sectionId="__brainstorm__"
              initialIdea={brainstormSeed}
            />
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
      </GlassSurface>
    );
  }

  // ── A piece is open: the outline + repository loop. ──
  // Dense-legible-keep-opaque (SPR-03 M3 / rigor #1): the open piece is the
  // dense Write IDE (outline + block repository + canvas). It stays OPAQUE via
  // GlassSurface variant="solid" — same hue at alpha 1, no scene behind to
  // erode contrast. Transparency here would risk the body text M3 protects;
  // the honest choice is solid, exactly like the /inv/:id research IDE.
  return (
    <GlassSurface variant="solid" className="flex h-full min-h-0">
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
            {/* M1: the active research connection is shown at all times. The
                link is the read-back investigation_root_id (it EXISTS in the
                substrate, not a UI claim). */}
            {detail && (
              <p
                data-testid="active-connection"
                className="mt-0.5 text-[11px] text-ink-mute dark:text-moonlight"
              >
                {detail.investigation_root_id ? (
                  <>Connected to research · backing folder linked</>
                ) : (
                  <span className="text-emperor">No research connected</span>
                )}
              </p>
            )}
          </div>
          <div className="flex shrink-0 items-center gap-3">
            {/* M1: toggle to the imported SPR-03 Canvas of the linked research. */}
            {detail?.investigation_root_id && (
              <button
                type="button"
                onClick={() => setPieceView((v) => (v === "canvas" ? "outline" : "canvas"))}
                className="text-xs text-ink-soft underline hover:text-ink dark:text-starlight"
              >
                {pieceView === "canvas" ? "outline" : "research canvas"}
              </button>
            )}
            <button
              type="button"
              onClick={() => setOnRamp((v) => (v === "context" ? null : "context"))}
              className="text-xs text-ink-soft underline hover:text-ink dark:text-starlight"
            >
              {onRamp === "context" ? "hide brainstorm" : "brainstorm a section"}
            </button>
          </div>
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
          pieceView === "canvas" && detail.investigation_root_id ? (
            // M1: the SPR-03 Canvas, IMPORTED (not re-implemented) — it loads
            // the linked investigation's insight/question blocks onto the free
            // 2D canvas. Positions persist via the SPR-03 typed-event funnel.
            <div className="min-h-0 flex-1">
              <Canvas investigationId={detail.investigation_root_id} />
            </div>
          ) : (
            <Outline
              deliverableId={detail.deliverable_id}
              sections={detail.sections}
              onChanged={refresh}
              registerAddHandler={registerAddHandler}
              investigationId={detail.investigation_root_id}
            />
          )
        ) : (
          <p className="font-serif text-sm italic text-ink-mute dark:text-moonlight">
            {loading ? "Opening the piece…" : "That piece isn't available."}
          </p>
        )}
      </main>

      <aside className="hidden w-80 shrink-0 flex-col border-l border-rule bg-ice-0 p-4 dark:border-charcoal-1 dark:bg-charcoal-2 lg:flex">
        <BlockRepository onAdd={(hit) => addHandler.current(hit)} />
      </aside>
    </GlassSurface>
  );
}
