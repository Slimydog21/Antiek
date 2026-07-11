/**
 * Midnight Oil mode shell — unattended deep research entry.
 *
 * Mounts PriceCeilingPanel (#828) so operators can set hours + goals and
 * review an advisory USD ceiling before approving unattended work.
 * Does not own the panel implementation or App router registration.
 */

import PriceCeilingPanel from "./PriceCeilingPanel";

export default function MidnightOilMode() {
  return (
    <div
      className="midnight-oil-mode flex flex-col gap-4 p-4"
      data-testid="midnight-oil-mode"
      aria-label="Midnight Oil"
    >
      <header data-testid="midnight-oil-header">
        <h1 className="font-mono text-sm uppercase tracking-wider">
          Midnight Oil
        </h1>
        <p className="text-sm opacity-80" data-testid="midnight-oil-blurb">
          Unattended deep research: set a work window and goals, approve a
          recommended price ceiling, then let the swarm execute. Advisory
          ceilings never spend until you approve.
        </p>
      </header>
      <section data-testid="midnight-oil-ceiling-slot">
        <PriceCeilingPanel />
      </section>
    </div>
  );
}
