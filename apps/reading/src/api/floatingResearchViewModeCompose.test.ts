import { describe, expect, it } from "vitest";
import {
  markFloatingCompleted,
  spawnFloatingFromHighlight,
} from "./floatingDeepResearch";
import {
  assessFloatingViewModeCapabilities,
  composeFloatingResearchViewMode,
  formatFloatingViewModeComposeSummary,
} from "./floatingResearchViewModeCompose";

function baseInstance() {
  return spawnFloatingFromHighlight({
    parent_asset_id: "asset-read-1",
    highlight: "scaling laws under noise",
    gated: false,
  });
}

describe("assessFloatingViewModeCapabilities", () => {
  it("allows float/fullscreen/draft on proposed; full only when completed", () => {
    const inst = baseInstance();
    const caps = assessFloatingViewModeCapabilities(inst);
    expect(caps.can_float).toBe(true);
    expect(caps.can_fullscreen).toBe(true);
    expect(caps.can_draft_merge).toBe(true);
    expect(caps.can_full_merge).toBe(false);
    expect(caps.current_view_mode).toBe("floating");
  });

  it("allows full merge only when completed", () => {
    const inst = markFloatingCompleted(baseInstance());
    const caps = assessFloatingViewModeCapabilities(inst);
    expect(caps.can_full_merge).toBe(true);
    expect(caps.can_draft_merge).toBe(true);
  });
});

describe("composeFloatingResearchViewMode", () => {
  it("float → floating and honesty flags false", () => {
    let inst = baseInstance();
    const c = composeFloatingResearchViewMode({
      instance: inst,
      action: "fullscreen",
    });
    expect(c.view_mode).toBe("fullscreen");
    expect(c.live_dispatched).toBe(false);
    expect(c.merge_executed).toBe(false);
    expect(c.merge_intent).toBeNull();
    expect(c.action_applied).toBe(true);
    expect(c.authority).toBe("floating_research_view_mode_compose_advisory");

    const back = composeFloatingResearchViewMode({
      instance: c.instance,
      action: "float",
    });
    expect(back.view_mode).toBe("floating");
    expect(back.live_dispatched).toBe(false);
    expect(back.merge_executed).toBe(false);
    expect(formatFloatingViewModeComposeSummary(back)).toMatch(
      /live_dispatched=false/,
    );
  });

  it("fullscreen → fullscreen without dispatch", () => {
    const c = composeFloatingResearchViewMode({
      instance: baseInstance(),
      action: "fullscreen",
    });
    expect(c.view_mode).toBe("fullscreen");
    expect(c.instance.status).toBe("open");
    expect(c.live_dispatched).toBe(false);
    expect(c.merge_executed).toBe(false);
  });

  it("propose_draft_merge yields intent only", () => {
    const c = composeFloatingResearchViewMode({
      instance: baseInstance(),
      action: "propose_draft_merge",
    });
    expect(c.merge_intent).not.toBeNull();
    expect(c.merge_intent!.kind).toBe("draft_merge");
    expect(c.merge_intent!.merge_executed).toBe(false);
    expect(c.merge_executed).toBe(false);
    expect(c.live_dispatched).toBe(false);
    // view mode stays non-merged
    expect(c.view_mode).not.toBe("merged_draft");
    expect(c.view_mode).not.toBe("merged_full");
  });

  it("propose_full_merge requires completed + operator_ack", () => {
    expect(() =>
      composeFloatingResearchViewMode({
        instance: baseInstance(),
        action: "propose_full_merge",
        operator_ack: true,
      }),
    ).toThrow(/completed/);

    const completed = markFloatingCompleted(baseInstance());
    expect(() =>
      composeFloatingResearchViewMode({
        instance: completed,
        action: "propose_full_merge",
        operator_ack: false,
      }),
    ).toThrow(/operator_ack/);

    expect(() =>
      composeFloatingResearchViewMode({
        instance: completed,
        action: "propose_full_merge",
      }),
    ).toThrow(/operator_ack/);

    const c = composeFloatingResearchViewMode({
      instance: completed,
      action: "propose_full_merge",
      operator_ack: true,
    });
    expect(c.merge_intent!.kind).toBe("full_merge");
    expect(c.merge_intent!.merge_executed).toBe(false);
    expect(c.merge_executed).toBe(false);
    expect(c.live_dispatched).toBe(false);
  });

  it("rejects invalid action and broken honesty flags", () => {
    expect(() =>
      composeFloatingResearchViewMode({
        instance: baseInstance(),
        // @ts-expect-error intentional invalid
        action: "teleport",
      }),
    ).toThrow(/action must be/);

    const bad = {
      ...baseInstance(),
      live_dispatched: true as unknown as false,
    };
    expect(() =>
      composeFloatingResearchViewMode({
        instance: bad,
        action: "float",
      }),
    ).toThrow(/live_dispatched/);
  });
});
