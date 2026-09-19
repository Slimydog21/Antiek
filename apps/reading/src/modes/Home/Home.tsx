import { useNavigate } from "react-router-dom";

import BrainMascot from "../../brand/BrainMascot";
import GlassSurface from "../../shell/GlassSurface";
import {
  WORKFLOWS,
  WORKFLOW_ORDER,
} from "../../shell/workflowTaxonomy";

/**
 * Home (SPR-12 M1) — the unified branded front door.
 *
 * The operator's brief: land somewhere branded that says what Antiek IS
 * and lets you jump straight in the driver's seat — "point guard with the
 * whole team at your disposal," never a cold empty surface. So this is a
 * warm orientation page, not an AI-marketing splash: one honest statement
 * of what the thing is, four equal doors each ONE CLICK into its surface,
 * and biographies featured as a real thing you can start.
 *
 * ─── ROUTING DECISION (reversible, recorded per the sprint adjudication) ──
 * This renders at a NEW /home route. The top-left rail logo points here.
 * "/" stays the Research door (StartResearch already serves that landing).
 * The rejected alternative — make "/" itself the Home and move Research to
 * /research — was passed over for blast radius (every "/" deep-link, the
 * workflowForPath default, the rail active-state, the catch-all redirect,
 * and StartResearch's own /inv navigation would have to move). If a future
 * operator wants Home as the literal root, flip the route in App.tsx and
 * repoint workflowForPath's "/" default; nothing here assumes /home.
 * ─────────────────────────────────────────────────────────────────────────
 *
 * §5 voice discipline: every line is crafted prose in the product's own
 * register — no em-dashes-as-filler, no "(high confidence)", no generic
 * "supercharge your workflow" slop. The cards lead with the verb you do.
 *
 * The four cards read their label + tagline + route from workflowTaxonomy
 * (the single source of truth), so a door re-home (e.g. Read → /library)
 * is honoured here automatically and the home can never drift from the
 * rail's idea of where a door goes.
 */

/** One-line, surface-specific verb for each door — the FIRST thing you do
 *  when you walk through it. Kept here (presentation) rather than in the
 *  taxonomy, which stays free of home-copy. Voice-matched to each
 *  surface's own landing (StartResearch, Library, WriteHome, SpeakIndex). */
const DOOR_VERB: Record<(typeof WORKFLOW_ORDER)[number], string> = {
  research: "Ask a question and get a cited, graded answer.",
  read: "Open a book and read it with the AI alongside.",
  write: "Pull your notes into an outline, then draft from them.",
  speak: "Remember someone, and gather the voices who knew them.",
};

export function Home() {
  const navigate = useNavigate();

  return (
    // Landing-glass (SPR-03 M2): the Home front door is a LANDING surface, so
    // its full-bleed root renders through GlassSurface — the mountainscape
    // <Scene/> (z-0) shows through the translucent fill, and the scrim keeps the
    // brand statement legible (WCAG-AA owned by GlassSurface, not this body).
    // Was an opaque bg-ice-2 dark:bg-space-2 wall that occluded the scene.
    <GlassSurface className="h-full w-full overflow-y-auto">
      <div className="mx-auto max-w-3xl px-6 py-14">
        {/* Brand statement — what Antiek is, in its own voice. */}
        <header className="mb-10 flex flex-col items-center text-center">
          <BrainMascot mood="idle" size={72} label="Antiek" />
          <h1 className="mt-4 font-serif text-3xl font-semibold text-ink dark:text-bright">
            One workspace for everything you read, research, and write.
          </h1>
          <p className="mt-3 max-w-xl font-serif text-[15px] leading-relaxed text-shadow-1 dark:text-moonlight">
            Antiek keeps every book, note, and finding on one substrate, so a
            question you ask in research can pull from a book you read last
            month and land in a draft you are writing now. Pick where you want
            to start.
          </p>
        </header>

        {/* Four equal doors. Each is one click into its surface. */}
        <nav
          aria-label="Workflows"
          data-testid="home-workflow-cards"
          className="grid grid-cols-1 gap-4 sm:grid-cols-2"
        >
          {WORKFLOW_ORDER.map((wf) => {
            const meta = WORKFLOWS[wf];
            return (
              <button
                key={wf}
                type="button"
                data-workflow={wf}
                onClick={() => navigate(meta.defaultRoute)}
                className={
                  "group flex flex-col items-start rounded-hog border-edge border-sun " +
                  "bg-ice-0 p-5 text-left shadow-z1 transition " +
                  "hover:shadow-z2 hover:-translate-y-0.5 " +
                  "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sun " +
                  "dark:bg-charcoal-2"
                }
              >
                <span className="font-serif text-lg font-semibold text-ink dark:text-bright">
                  {meta.label}
                </span>
                <span className="mt-1 text-[13.5px] leading-relaxed text-shadow-1 dark:text-moonlight">
                  {DOOR_VERB[wf]}
                </span>
              </button>
            );
          })}
        </nav>

        {/* Biographies — featured (SPR-11). A biography is a TEMPLATE that
            composes research, writing, and gathered voices over the one
            workspace — not a separate place. The CTA opens the dedicated
            /biography landing where the guided flow begins. */}
        <section
          aria-label="Biographies"
          data-testid="home-biographies"
          className="mt-8 rounded-hog border-edge border-sun bg-sun/10 p-5 dark:bg-sun/5"
        >
          <div className="flex items-start gap-4">
            <BrainMascot mood="celebrate" size={48} label="" />
            <div className="min-w-0">
              <h2 className="font-serif text-lg font-semibold text-ink dark:text-bright">
                Write someone&rsquo;s biography
              </h2>
              <p className="mt-1 text-[13.5px] leading-relaxed text-shadow-1 dark:text-moonlight">
                Start with a person you want to remember, invite the people who
                knew them, and gather their voices. The research you do, the
                draft you write, and the voices you collect all live together
                in one place, so each one feeds the others.
              </p>
              <button
                type="button"
                data-testid="home-biographies-cta"
                onClick={() => navigate("/biography")}
                className={
                  "mt-3 inline-flex items-center rounded-hog border-edge border-sun " +
                  "bg-sun px-3 py-1.5 text-[13px] font-semibold text-ink shadow-z1 transition " +
                  "hover:shadow-z2 focus-visible:outline focus-visible:outline-2 " +
                  "focus-visible:outline-offset-2 focus-visible:outline-ink"
                }
              >
                Start a biography
              </button>
            </div>
          </div>
        </section>
      </div>
    </GlassSurface>
  );
}

export default Home;
