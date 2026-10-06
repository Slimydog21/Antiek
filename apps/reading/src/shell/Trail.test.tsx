/**
 * Trail.test.tsx — G-X3 (GAPS §8): the Trail must not say "thread".
 *
 * "Thread" now means one subagent investigation (GAPS §1.0). The Trail is an
 * entity's lineage across workflows (served by GET /thread/{node_id}; the
 * backend route keeps its name). The old copy ("Thread integrity error"), its
 * aria-label ("Cross-workflow thread") and the `thread-*` test ids survived the
 * component rename and are wrong vocabulary in the UI. This suite pins the
 * Trail/lineage naming — it is red on the pre-rename component.
 */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import { Trail } from "./Trail";
import type { Thread, ThreadHop } from "./threadModel";

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

// Order matters: the unbuilt write hop first (honest stub), then two built
// hops sharing the canonical id. The last of those is the current step.
const TRAIL: Thread = {
  canonicalEntityId: CANONICAL,
  canonicalEntityKind: "insight_node",
  isDegenerate: false,
  hops: [
    hop("write", {
      seamEventId: "evt-read2write",
      seamActionType: "seam.read_to_write",
      built: false,
    }),
    hop("research"),
    hop("read", { seamEventId: "evt-r2read", seamActionType: "seam.research_to_read" }),
  ],
  stubs: [],
};

const FORKED: Thread = {
  canonicalEntityId: CANONICAL,
  canonicalEntityKind: "insight_node",
  isDegenerate: false,
  hops: [hop("research"), hop("read", { entityId: "insight-copy-9" })],
  stubs: [],
};

describe("G-X3 — the Trail speaks Trail/lineage, never 'thread'", () => {
  it("the trail is labelled as a cross-workflow trail and keyed trail-*", () => {
    render(<Trail thread={TRAIL} />);
    const nav = screen.getByRole("navigation");
    expect(nav.getAttribute("aria-label")).toBe("Cross-workflow trail");
    expect(document.querySelector('[data-testid="trail-breadcrumb"]')).toBeTruthy();
    expect(document.querySelector('[data-testid="thread-breadcrumb"]')).toBeNull();
  });

  it("hop segments use trail-* test ids (built, current, and honest stubs)", () => {
    render(<Trail thread={TRAIL} activeEntityId="insight-7f3a9c" />);
    // The built research hop is a non-current segment → clickable.
    expect(document.querySelector('[data-testid="trail-hop-research"]')).toBeTruthy();
    // The read hop holds the active entity last → the current step.
    expect(document.querySelector('[data-testid="trail-hop-current-read"]')).toBeTruthy();
    // The unbuilt write hop is the honest stub.
    expect(document.querySelector('[data-testid="trail-hop-stub-write"]')).toBeTruthy();
    expect(document.querySelector('[data-testid^="thread-hop-"]')).toBeNull();
  });

  it("the fork integrity warning is a Trail/lineage warning, not a 'thread' one", () => {
    render(<Trail thread={FORKED} />);
    const alert = screen.getByRole("alert");
    expect(alert.getAttribute("data-testid")).toBe("trail-breadcrumb-integrity-warning");
    expect(alert.textContent ?? "").toContain("Trail integrity error");
    expect(alert.textContent ?? "").not.toMatch(/thread/i);
  });
});
