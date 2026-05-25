import {
  WORKFLOWS,
  modesForWorkflow,
  workflowHasBuiltMode,
  type Workflow,
} from "./workflowTaxonomy";

/**
 * WorkflowStub (SPR-04 milestone 5) — the honest "not yet" surface for a
 * workflow whose product isn't built.
 *
 * The honesty contract:
 *   - It NEVER presents absent capability as present (no fake screen).
 *   - Whether it shows at all is keyed to REAL build presence read from
 *     the taxonomy's `built` flags (which taxonomy.test.ts pins to the
 *     actual route table). So "is Write built?" is answered by code, not
 *     by a hardcoded list a maintainer forgets to update.
 *   - It says plainly what's coming and which modes are pending, so the
 *     operator sees the product's true shape.
 *
 * Usage: a workflow scene renders <WorkflowStub workflow="write" /> only
 * when `!workflowHasBuiltMode("write")`. The component itself also guards
 * (renders a "this workflow is built" note if called for a built
 * workflow) so a misuse is loud, not silent.
 */
export function WorkflowStub({
  workflow,
  /**
   * STORYBOOK / TEST ONLY — force the unbuilt branch to render so the
   * "not yet" state can be visually regression-tested even when every
   * real workflow has a built surface today. Production callers MUST NOT
   * pass this: the default (undefined) reads real build presence from the
   * taxonomy, which is the whole point. Documented + named loudly so a
   * production misuse is obvious in review.
   */
  forceUnbuiltForStory,
}: {
  workflow: Exclude<Workflow, "shared">;
  forceUnbuiltForStory?: boolean;
}) {
  const meta = WORKFLOWS[workflow];
  const built = forceUnbuiltForStory ? false : workflowHasBuiltMode(workflow);
  const modes = modesForWorkflow(workflow);
  const pending = modes.filter((m) => !m.built);

  // Misuse guard — loud, not silent. If someone renders the stub for a
  // workflow that IS built, surface that fact rather than lying.
  if (built) {
    return (
      <div
        className="h-full w-full flex items-center justify-center p-12"
        data-testid={`workflow-stub-misuse-${workflow}`}
      >
        <div className="max-w-md text-center">
          <p className="font-mono text-[11px] uppercase tracking-wider text-shadow-1 dark:text-moonlight">
            {meta.label}
          </p>
          <p className="mt-2 text-sm text-ink dark:text-bright">
            This workflow has built surfaces — render its scene, not this
            stub.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div
      className="h-full w-full flex items-center justify-center p-12"
      data-testid={`workflow-stub-${workflow}`}
    >
      <div className="max-w-lg text-center">
        <p className="font-mono text-[11px] uppercase tracking-wider text-shadow-1 dark:text-moonlight">
          {meta.label}
        </p>
        <h1 className="mt-3 font-serif text-2xl text-ink dark:text-bright">
          Not yet — {meta.label} is on the way.
        </h1>
        <p className="mt-3 text-[15px] leading-relaxed text-ink-soft dark:text-starlight font-serif">
          {meta.tagline}{" "}
          {meta.shippingSprint
            ? `Shipping in ${meta.shippingSprint}.`
            : "Shipping in a later sprint."}
        </p>

        {pending.length > 0 && (
          <div className="mt-6 inline-block text-left">
            <p className="font-mono text-[11px] uppercase tracking-wider text-shadow-1 dark:text-moonlight mb-2">
              Pending surfaces
            </p>
            <ul className="space-y-1">
              {pending.map((m) => (
                <li
                  key={m.id}
                  className="text-[13px] text-ink-soft dark:text-starlight flex items-baseline gap-2"
                >
                  <span aria-hidden="true" className="text-ink-mute dark:text-moonlight">
                    ·
                  </span>
                  <span>
                    <span className="text-ink dark:text-bright">{m.label}</span>
                    {" — "}
                    {m.blurb}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}

export default WorkflowStub;
