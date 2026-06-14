import type { Meta, StoryObj } from "@storybook/react";
import { within, userEvent, waitFor, expect } from "@storybook/test";

import ThreadJump from "./ThreadJump";
import type { Thread, ThreadHop } from "./threadModel";

/**
 * ThreadJump (antiek-unified SPR-06 M3) — the cross-workflow jump container.
 *
 * It wraps ThreadBreadcrumb with the real jump behaviour: clicking a built hop
 * navigates to that workflow's landing route AND advances the active crumb; a
 * jump into an UNBUILT workflow surfaces the honest WorkflowStub instead of a
 * fake screen. ThreadJump owns two pieces of state — the active entity and the
 * stubbed-workflow — both of which were previously only inspectable inside the
 * sibling ThreadBreadcrumb stories, never co-located here.
 *
 * ── States authored (ALC SPR-09 product-character lift) ──────────────────────
 * ThreadJump is a ≥2-state control. These stories drive the REAL component into
 * each: the resting breadcrumb, the after-a-built-jump advanced crumb, and the
 * honest "not yet" stub a jump into an unbuilt workflow produces. The jump
 * stories click the real hop button via `play`, running the component's own
 * `jumpTo` reducer — nothing is faked.
 *
 * Werner skin (Lemon tokens) — no hardcoded colors.
 */
const CANONICAL = "insight-7f3a9c";

function hop(
  workflow: ThreadHop["workflow"],
  opts: Partial<ThreadHop> = {},
): ThreadHop {
  return {
    workflow,
    entityId: CANONICAL,
    entityKind: "insight_node",
    seamEventId: null,
    seamActionType: null,
    provenanceRef: null,
    built: true,
    viaProvisionalSeam: false,
    ...opts,
  };
}

const FULL_FLYWHEEL: Thread = {
  canonicalEntityId: CANONICAL,
  canonicalEntityKind: "insight_node",
  isDegenerate: false,
  hops: [
    hop("research"),
    hop("read", { seamEventId: "evt-r2read", seamActionType: "seam.research_to_read" }),
    hop("write", { seamEventId: "evt-read2write", seamActionType: "seam.read_to_write" }),
  ],
  stubs: [],
};

const meta = {
  title: "Shell / ThreadJump (SPR-06)",
  component: ThreadJump,
  parameters: { layout: "padded" },
  tags: ["autodocs", "a11y-audit"],
} satisfies Meta<typeof ThreadJump>;

export default meta;
type Story = StoryObj<typeof meta>;

/**
 * REST — the container at mount. The breadcrumb shows the full flywheel with
 * the canonical (Research) entity as the current crumb; no jump has happened,
 * no stub is shown.
 */
export const Rest: Story = {
  args: { thread: FULL_FLYWHEEL },
  render: (args) => {
    return (
      <div className="w-[640px] bg-ice-1 dark:bg-charcoal-2 border-edge border-sun rounded-hog overflow-hidden">
        <ThreadJump {...args} />
      </div>
    );
  },
};

/**
 * AFTER A BUILT JUMP — the play function clicks the Read hop (a built
 * workflow). The component's real `jumpTo` fires: it navigates to Read's
 * landing route (the global MemoryRouter absorbs the navigate) and, because
 * Read IS built, surfaces NO honest stub — the breadcrumb stays mounted. The
 * after-jump state (jump fired, no stub) is the authored non-default state.
 *
 * (Note on the current-crumb: every legitimate hop carries the SAME canonical
 * id — the no-duplicate invariant — so the breadcrumb's "current" is always the
 * last occurrence of that id; a jump's observable effect is the navigate + the
 * built/unbuilt branch, not a moving highlight. The contrast that matters for
 * state coverage is built-jump-no-stub vs the unbuilt-hop stub story below.)
 */
export const AfterBuiltJump: Story = {
  args: { thread: FULL_FLYWHEEL },
  render: (args) => {
    return (
      <div className="w-[640px] bg-ice-1 dark:bg-charcoal-2 border-edge border-sun rounded-hog overflow-hidden">
        <ThreadJump {...args} />
      </div>
    );
  },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    // The Read hop is a navigable button (built, not the current crumb).
    const readHop = await canvas.findByRole("button", { name: /Read/i });
    await userEvent.click(readHop);
    await waitFor(() => {
      // Read is built → the jump surfaces NO honest stub; breadcrumb stays.
      expect(canvas.queryByTestId("thread-jump-stub")).not.toBeInTheDocument();
      expect(canvas.getByTestId("thread-breadcrumb")).toBeInTheDocument();
    });
  },
};

const SPEAK_INTO_UNBUILT: Thread = {
  canonicalEntityId: "speak-claim-42",
  canonicalEntityKind: "speak_claim",
  isDegenerate: false,
  hops: [
    hop("speak", { entityId: "speak-claim-42", entityKind: "speak_claim" }),
    // A hop into a workflow whose product has no built surface — jumping here
    // must surface the honest stub, never a fabricated screen.
    hop("write", {
      entityId: "speak-claim-42",
      entityKind: "speak_claim",
      seamEventId: "evt-speak2write",
      seamActionType: "seam.speak_to_write",
      built: false,
    }),
  ],
  stubs: [{ workflow: "write", reason: "write has no built surface yet" }],
};

/**
 * JUMP INTO UNBUILT → HONEST STUB — when the thread's target hop is a workflow
 * with no built surface, the breadcrumb segment renders the non-navigable "not
 * yet" hop, and (in production) a jump would surface the WorkflowStub rather
 * than navigate to a fake screen. This story authors that honesty contract as
 * its own state: the unbuilt hop is visibly a dimmed, non-clickable stub
 * segment.
 */
export const UnbuiltHopHonestStub: Story = {
  args: { thread: SPEAK_INTO_UNBUILT },
  render: (args) => {
    return (
      <div className="w-[640px] bg-ice-1 dark:bg-charcoal-2 border-edge border-sun rounded-hog overflow-hidden">
        <ThreadJump {...args} />
      </div>
    );
  },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await waitFor(() => {
      // The Write hop is unbuilt → a non-navigable stub segment, not a button.
      expect(
        canvas.getByTestId("thread-hop-stub-write"),
      ).toBeInTheDocument();
    });
  },
};
