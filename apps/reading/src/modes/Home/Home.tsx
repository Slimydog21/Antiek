import { useState } from "react";
import { useNavigate } from "react-router-dom";

import Werner from "../../brand/Werner";
import GlassSurface from "../../shell/GlassSurface";
import {
  WORKFLOWS,
  WORKFLOW_ORDER,
} from "../../shell/workflowTaxonomy";
import campusEnvironment from "./home_alpine_knowledge_campus_v1.webp";

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

/** Desktop placement belongs to this authored Home composition—not to the
 * product taxonomy. DOM order remains WORKFLOW_ORDER at every breakpoint. */
const CAMPUS_REGION: Record<
  (typeof WORKFLOW_ORDER)[number],
  { landmark: string; placement: string; marker: string }
> = {
  research: {
    landmark: "Observatory",
    placement: "md:left-[8%] md:top-[26%] lg:top-[33%]",
    marker: "01",
  },
  read: {
    landmark: "Glacial archive",
    placement: "md:right-[7%] md:top-[28%] lg:top-[34%]",
    marker: "02",
  },
  write: {
    landmark: "Scriptorium",
    placement: "md:left-[11%] md:bottom-[10%]",
    marker: "03",
  },
  speak: {
    landmark: "Listening bowl",
    placement: "md:right-[10%] md:bottom-[9%]",
    marker: "04",
  },
};

export function Home() {
  const navigate = useNavigate();
  const [mapImageAvailable, setMapImageAvailable] = useState(true);
  const [mapImageReady, setMapImageReady] = useState(false);

  return (
    // Landing-glass (SPR-03 M2): the Home front door is a LANDING surface, so
    // its full-bleed root renders through GlassSurface — the mountainscape
    // <Scene/> (z-0) shows through the translucent fill, and the scrim keeps the
    // brand statement legible (WCAG-AA owned by GlassSurface, not this body).
    // Was an opaque bg-ice-2 dark:bg-space-2 wall that occluded the scene.
    <GlassSurface className="h-full w-full overflow-y-auto">
      <div className="mx-auto max-w-6xl px-4 py-6 sm:px-6 sm:py-10">
        <section className="relative">
        {/* Brand statement — what Antiek is, in its own voice. */}
        <header className="mx-auto mb-6 flex max-w-3xl flex-col items-center text-center lg:absolute lg:left-1/2 lg:top-5 lg:z-20 lg:mb-0 lg:w-[62%] lg:-translate-x-1/2 lg:rounded-hog lg:border lg:border-glass lg:bg-ice-0/90 lg:px-5 lg:py-4 lg:shadow-z1 lg:backdrop-blur-sm dark:lg:bg-charcoal-2/90">
          <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-shadow-1 dark:text-moonlight">
            Antiek · alpine knowledge campus
          </p>
          <h1 className="mt-2 font-serif text-3xl font-semibold text-ink dark:text-bright sm:text-4xl lg:text-3xl">
            One workspace for everything you read, research, and write.
          </h1>
          <p className="mt-3 max-w-xl font-serif text-[15px] leading-relaxed text-shadow-1 dark:text-moonlight lg:mt-2 lg:text-[13.5px] lg:leading-5">
            Antiek keeps every book, note, and finding on one substrate, so a
            question you ask in research can pull from a book you read last
            month and land in a draft you are writing now. Pick where you want
            to start.
          </p>
        </header>

        {/* The image owns geography only. The four destinations below are real
            HTML buttons in stable taxonomy order; their desktop positions are
            presentation, never hit-test or routing authority. */}
        <nav
          aria-label="Workflows"
          aria-describedby="home-campus-instructions"
          data-testid="home-workflow-cards"
          data-campus-map=""
          data-campus-image-ready={mapImageReady ? "true" : "false"}
          className="relative isolate overflow-hidden rounded-hog-lg border-edge border-sun bg-ice-3 shadow-z2 dark:bg-space-2 md:aspect-[1.56/1] lg:h-[calc(100vh-3rem)] lg:min-h-[600px] lg:max-h-[700px] lg:aspect-auto"
        >
          {mapImageAvailable && (
            <img
              src={campusEnvironment}
              alt=""
              aria-hidden="true"
              draggable={false}
              decoding="async"
              onLoad={() => setMapImageReady(true)}
              onError={() => {
                setMapImageReady(false);
                setMapImageAvailable(false);
              }}
              className="pointer-events-none h-56 w-full object-cover object-center md:absolute md:inset-0 md:h-full"
            />
          )}
          <div
            aria-hidden="true"
            className="pointer-events-none absolute inset-0 bg-gradient-to-b from-space-2/10 via-transparent to-space-2/30"
          />
          <p id="home-campus-instructions" className="sr-only">
            Four destinations share one campus. Move through the buttons in
            order to open Research, Read, Write, or Speak.
          </p>
          <ol className="relative z-10 grid gap-3 p-4 md:absolute md:inset-0 md:block md:p-0">
          {WORKFLOW_ORDER.map((wf) => {
            const meta = WORKFLOWS[wf];
            const region = CAMPUS_REGION[wf];
            return (
              <li key={wf} className={`md:absolute md:w-[31%] ${region.placement}`}>
                <button
                  type="button"
                  data-workflow={wf}
                  data-campus-region={region.landmark}
                  onClick={() => navigate(meta.defaultRoute)}
                  className={
                    "group flex w-full items-start gap-3 rounded-hog border-edge border-sun " +
                    "bg-ice-0/95 p-4 text-left shadow-z1 backdrop-blur-sm transition " +
                    "hover:-translate-y-0.5 hover:shadow-z2 " +
                    "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sun " +
                    "dark:bg-charcoal-2/95"
                  }
                >
                  <span
                    aria-hidden="true"
                    className="grid h-8 w-8 shrink-0 place-items-center rounded-full border border-sun bg-sun font-mono text-[11px] font-bold text-ink"
                  >
                    {region.marker}
                  </span>
                  <span className="min-w-0">
                    <span className="block font-mono text-[10px] uppercase tracking-[0.14em] text-shadow-1 dark:text-moonlight">
                      {region.landmark}
                    </span>
                    <span className="mt-0.5 block font-serif text-lg font-semibold text-ink dark:text-bright">
                      {meta.label}
                    </span>
                    <span className="mt-1 block text-[12.5px] leading-relaxed text-shadow-1 dark:text-moonlight">
                      {DOOR_VERB[wf]}
                    </span>
                  </span>
                </button>
              </li>
            );
          })}
          </ol>
        </nav>
        </section>

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
            <Werner mood="celebrate" size={48} label="" />
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
