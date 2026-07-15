import { useEffect, useState } from "react";
import type { Meta, StoryObj } from "@storybook/react";

import { PenguinMascot } from "../shell/PenguinMascot";
import { usePrefersReducedMotion } from "../workspace/usePrefersReducedMotion";
import {
  getActivity,
  type ActivityId,
  type StationActivity,
} from "./activities";
import { wernerIceFishingCursor } from "./iceFishingFlags";

interface AtlasEntry {
  id: ActivityId;
  workflow: string;
  route: string;
  job: string;
  boundary: string;
}

const entries: readonly AtlasEntry[] = [
  {
    id: "research-lens",
    workflow: "Research + Read",
    route: "/brainstorm · /library · /read/:id",
    job: "Inspect evidence without inspecting document pixels.",
    boundary:
      "No selection, content, provenance, network, or research authority.",
  },
  {
    id: "writing-nib",
    workflow: "Write",
    route: "/write · /create",
    job: "Place the drafting hotspot exactly where the operator acts.",
    boundary:
      "No editor mutation, save, navigation, content, or spend authority.",
  },
  {
    id: "speaking-resonance",
    workflow: "Speak",
    route: "/speak · /speak/invite/:token · /biography",
    job: "Signal listening posture without pretending to record.",
    boundary:
      "No microphone, audio, transcript, consent, or network authority.",
  },
  {
    id: "ice-fishing",
    workflow: "Shared + unknown",
    route: "/settings · unknown fallback",
    job: "Keep Werner’s original cursor-bait relationship as the safe default.",
    boundary: "No route, product, network, or mascot-position authority.",
  },
] as const;

function requiredActivity(id: ActivityId): StationActivity {
  const activity = getActivity(id);
  if (!activity) throw new Error(`Atlas requires registered activity ${id}`);
  return activity;
}

export function StationInstrumentAtlas() {
  const [selected, setSelected] = useState<ActivityId>("research-lens");
  const entry = entries.find((candidate) => candidate.id === selected)!;
  const activity = requiredActivity(selected);
  const Instrument = activity.instrument.render;
  const reduceMotion = usePrefersReducedMotion();
  const available = selected !== "ice-fishing" || wernerIceFishingCursor;
  const active = available && !reduceMotion;

  useEffect(() => {
    const root = document.documentElement;
    if (active) root.classList.add("werner-ice-cursor-hidden");
    else root.classList.remove("werner-ice-cursor-hidden");
    return () => root.classList.remove("werner-ice-cursor-hidden");
  }, [active]);

  return (
    <main className="min-h-screen bg-card-soft p-8 text-ink dark:text-bright">
      <header className="mx-auto max-w-6xl border-b-2 border-rule pb-6">
        <p className="font-mono text-xs uppercase tracking-widest text-shadow-1">
          Werner station · instrument atlas
        </p>
        <h1 className="mt-3 max-w-4xl font-serif text-3xl leading-tight">
          Werner stays home. The cursor changes jobs.
        </h1>
        <p className="mt-4 max-w-3xl font-serif text-lg leading-8">
          One deterministic grammar across Antiek’s four workflows. Select a
          station instrument, move it over the real HTML desk, and audit the
          capability it deliberately does not receive.
        </p>
      </header>

      <div className="mx-auto mt-7 grid max-w-6xl gap-7 lg:grid-cols-[0.8fr_1.2fr]">
        <nav aria-label="Station instruments" className="space-y-3">
          {entries.map((candidate) => {
            const active = candidate.id === selected;
            return (
              <button
                key={candidate.id}
                type="button"
                aria-pressed={active}
                onClick={() => setSelected(candidate.id)}
                className={`w-full rounded-hog-lg border-edge border-rule p-4 text-left font-serif shadow-z1 ${active ? "bg-sun-light-soft" : "bg-card"}`}
              >
                <span className="block font-mono text-xs uppercase tracking-widest text-shadow-1">
                  {candidate.workflow}
                </span>
                <strong className="mt-1 block text-lg">{candidate.id}</strong>
                <span className="mt-2 block text-sm">{candidate.route}</span>
              </button>
            );
          })}
        </nav>

        <section className="rounded-hog-lg border-edge border-rule bg-card p-8 shadow-z2">
          <p className="font-mono text-xs uppercase tracking-widest text-shadow-1">
            Active job · {entry.workflow}
          </p>
          <h2 className="mt-3 font-serif text-3xl leading-tight">
            {entry.job}
          </h2>
          <div className="mt-8 border-l-2 border-aurora pl-5">
            <p className="font-mono text-xs uppercase tracking-widest text-shadow-1">
              Authority withheld
            </p>
            <p className="mt-2 font-serif text-lg leading-8">
              {entry.boundary}
            </p>
          </div>
          <p className="mt-9 max-w-2xl font-serif text-lg leading-8">
            This review desk is selectable HTML. Generated concept frames can
            guide atmosphere, but never replace text, controls, provenance, or
            the operator’s exact interaction hotspot.
          </p>
          {!active && (
            <p className="mt-6 font-mono text-xs uppercase tracking-widest text-shadow-1">
              Native cursor preserved · custom instrument unavailable
            </p>
          )}
        </section>
      </div>

      <PenguinMascot />
      <Instrument disabled={!active} />
    </main>
  );
}

const meta = {
  title: "Werner / Station instruments / Complete atlas",
  component: StationInstrumentAtlas,
  parameters: { layout: "fullscreen" },
  tags: ["autodocs"],
} satisfies Meta<typeof StationInstrumentAtlas>;

export default meta;
type Story = StoryObj<typeof meta>;

export const FourWorkflowGrammar: Story = {};
