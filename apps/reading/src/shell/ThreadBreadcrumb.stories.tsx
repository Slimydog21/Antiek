import type { Meta, StoryObj } from "@storybook/react";

import ThreadBreadcrumb from "./ThreadBreadcrumb";
import ThreadJump from "./ThreadJump";
import type { Thread, ThreadHop } from "./threadModel";

/**
 * ThreadBreadcrumb (antiek-unified SPR-06) — the cross-workflow thread trail.
 *
 * Stories cover the SPR-06 acceptance surface:
 *   - a 1-hop (degenerate) thread,
 *   - a full-flywheel thread (Research → Read → Write → Read),
 *   - a thread crossing an UNBUILT workflow (honest "not yet" stub hop),
 *   - the integrity-warning state when a forked copy slips through (the
 *     breadcrumb refuses to render a continuity the data can't support),
 *   - the ThreadJump container that advances the breadcrumb on a jump.
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

const DEGENERATE: Thread = {
  canonicalEntityId: CANONICAL,
  canonicalEntityKind: "insight_node",
  isDegenerate: true,
  hops: [hop("research")],
  stubs: [],
};

const FULL_FLYWHEEL: Thread = {
  canonicalEntityId: CANONICAL,
  canonicalEntityKind: "insight_node",
  isDegenerate: false,
  hops: [
    hop("research"),
    hop("read", { seamEventId: "evt-r2read", seamActionType: "seam.research_to_read" }),
    hop("write", { seamEventId: "evt-read2write", seamActionType: "seam.read_to_write" }),
    hop("read", { seamEventId: "evt-write2read", seamActionType: "seam.write_to_read" }),
  ],
  stubs: [],
};

const WITH_UNBUILT_HOP: Thread = {
  canonicalEntityId: "speak-claim-42",
  canonicalEntityKind: "speak_claim",
  isDegenerate: false,
  hops: [
    hop("speak", { entityId: "speak-claim-42", entityKind: "speak_claim" }),
    // A hop into Write while Write is marked unbuilt — honest stub segment.
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

// A FORKED thread — the write→read hop holds a copy (different id). The server
// refuses to serve this (409); if it ever slipped through, the breadcrumb must
// refuse to render the trail. Story documents that honest-failure state.
const FORKED: Thread = {
  canonicalEntityId: CANONICAL,
  canonicalEntityKind: "insight_node",
  isDegenerate: false,
  hops: [
    hop("research"),
    hop("read", { seamEventId: "evt-r2read" }),
    hop("read", { entityId: `${CANONICAL}-COPY`, seamEventId: "evt-fork" }),
  ],
  stubs: [],
};

const meta = {
  title: "Shell / ThreadBreadcrumb (SPR-06)",
  component: ThreadBreadcrumb,
  parameters: { layout: "padded" },
  tags: ["autodocs"],
} satisfies Meta<typeof ThreadBreadcrumb>;

export default meta;
type Story = StoryObj<typeof meta>;

/** A degenerate 1-hop thread — the entity lives in one workflow. */
export const OneHopThread: Story = {
  args: { thread: DEGENERATE },
};

/** The full flywheel — Research → Read → Write → Read, same node id. */
export const FullFlywheelThread: Story = {
  args: { thread: FULL_FLYWHEEL },
};

/** A thread crossing an unbuilt workflow — the Write hop is an honest stub. */
export const WithUnbuiltHop: Story = {
  args: { thread: WITH_UNBUILT_HOP },
};

/** The integrity-warning state — a forked copy is present; trail suppressed. */
export const ForkedThreadSuppressed: Story = {
  args: { thread: FORKED },
};

/** The ThreadJump container — clicking a segment advances the breadcrumb. */
export const JumpAlongThread: StoryObj<typeof ThreadJump> = {
  render: () => <ThreadJump thread={FULL_FLYWHEEL} />,
};
