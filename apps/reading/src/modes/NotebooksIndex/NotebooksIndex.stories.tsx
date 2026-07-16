import type { Meta, StoryObj } from "@storybook/react";
import type { ReactNode } from "react";

import { RecursiveNotebookConservatoryFrame, type NotebookConservatoryPhase } from "./index";

const meta = {
  title: "Notebooks / Recursive Notebook Conservatory",
  component: RecursiveNotebookConservatoryFrame,
  parameters: { layout: "fullscreen", lostpixel: { waitBeforeScreenshot: 500 } },
  tags: ["autodocs", "a11y-audit"],
} satisfies Meta<typeof RecursiveNotebookConservatoryFrame>;
export default meta;
type Story = StoryObj<typeof meta>;

function Inventory({ counts = [7, 5, 2] }: { counts?: [number, number, number] }) {
  return <section className="recursive-notebook-conservatory__inventory" aria-label="Notebook inventory"><div><p className="recursive-notebook-conservatory__section-label">Living inventory</p><h2>Your working books</h2><p>Private working notebooks and public contributions remain visibly distinct.</p></div><div className="recursive-notebook-conservatory__counts"><span><strong>{counts[0]}</strong> total</span><span><strong>{counts[1]}</strong> private</span><span><strong>{counts[2]}</strong> public</span></div></section>;
}

function NewNotebook({ planting = false }: { planting?: boolean }) {
  return <form className="recursive-notebook-conservatory__new"><div><p className="recursive-notebook-conservatory__section-label">Plant a working book</p><h2>New notebook</h2></div><label><span>Notebook title</span><input readOnly value={planting ? "Models as research collaborators" : ""} placeholder="e.g. Models as research collaborators" /></label><label><span>Investigation ID <em>optional</em></span><input readOnly value={planting ? "inv-routing" : ""} placeholder="Bind this notebook to an investigation" /></label><button type="button">{planting ? "Planting notebook…" : "Create notebook"}</button></form>;
}

function Catalogue({ filtered = false, empty = false, failure = false }: { filtered?: boolean; empty?: boolean; failure?: boolean }) {
  return <section className="recursive-notebook-conservatory__catalogue" aria-label="Notebook catalogue"><div className="recursive-notebook-conservatory__catalogue-head"><div><p className="recursive-notebook-conservatory__section-label">Conservatory beds</p><h2>Notebook catalogue</h2></div><p>{empty ? 0 : filtered ? 2 : 7} of {empty ? 0 : 7}</p></div><div className="recursive-notebook-conservatory__filters" aria-label="Filter notebooks by content class"><button type="button" aria-pressed={!filtered}>all notebooks</button><button type="button" aria-pressed={filtered}>user owned</button><button type="button" aria-pressed={false}>user public contribution</button></div>{failure ? <p role="alert" className="recursive-notebook-conservatory__error">The notebook conservatory could not be surveyed. Try again.</p> : empty ? <p role="status" className="recursive-notebook-conservatory__status">No working books yet. Plant the first notebook above.</p> : <table className="w-full border-collapse text-left"><thead><tr><th>Title</th><th>Updated</th><th>Class</th></tr></thead><tbody><tr className="border-t border-rule"><td className="py-3 font-serif">Models as research collaborators</td><td className="font-mono text-xs">2026-07-15</td><td>user owned</td></tr><tr className="border-t border-rule"><td className="py-3 font-serif">Polar interface field notes</td><td className="font-mono text-xs">2026-07-14</td><td>{filtered ? "user owned" : "user public contribution"}</td></tr></tbody></table>}</section>;
}

function Fixture({ phase, production = false, children }: { phase: NotebookConservatoryPhase; production?: boolean; children: ReactNode }) {
  return <main className="h-screen"><RecursiveNotebookConservatoryFrame phase={phase} visualFixture={!production}><div className="recursive-notebook-conservatory__console space-y-6">{children}</div></RecursiveNotebookConservatoryFrame></main>;
}

export const Surveying: Story = { render: () => <Fixture phase="Surveying"><Inventory counts={[0, 0, 0]} /><NewNotebook /><p role="status" className="recursive-notebook-conservatory__status">Surveying the conservatory…</p></Fixture> };
export const EmptyBeds: Story = { render: () => <Fixture phase="Empty beds"><Inventory counts={[0, 0, 0]} /><NewNotebook /><Catalogue empty /></Fixture> };
export const Ready: Story = { render: () => <Fixture phase="Ready"><Inventory /><NewNotebook /><Catalogue /></Fixture> };
export const Filtered: Story = { render: () => <Fixture phase="Ready"><Inventory /><NewNotebook /><Catalogue filtered /></Fixture> };
export const Planting: Story = { render: () => <Fixture phase="Planting"><Inventory /><NewNotebook planting /><Catalogue /></Fixture> };
export const NeedsAttention: Story = { render: () => <Fixture phase="Needs attention"><Inventory counts={[0, 0, 0]} /><NewNotebook /><Catalogue failure /></Fixture> };
export const ProductionRaster: Story = { parameters: { lostpixel: { disable: true } }, render: () => <Fixture phase="Ready" production><Inventory /><NewNotebook /><Catalogue /></Fixture> };
