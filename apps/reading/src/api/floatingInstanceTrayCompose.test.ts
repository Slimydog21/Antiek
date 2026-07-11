import { describe, expect, it } from "vitest";
import {
  composeFloatingInstanceTray,
  formatFloatingInstanceTraySummary,
} from "./floatingInstanceTrayCompose";

const members = [
  {
    instance_id: "f1",
    parent_asset_id: "asset-1",
    status: "completed" as const,
    live_dispatched: false as const,
    merge_executed: false as const,
  },
  {
    instance_id: "f2",
    parent_asset_id: "asset-1",
    status: "open" as const,
    live_dispatched: false as const,
    merge_executed: false as const,
  },
  {
    instance_id: "f3",
    parent_asset_id: "asset-1",
    status: "completed" as const,
    live_dispatched: false as const,
    merge_executed: false as const,
  },
];

describe("composeFloatingInstanceTray", () => {
  it("collective pack multi-select without dispatch", () => {
    const c = composeFloatingInstanceTray({
      parent_asset_id: "asset-1",
      members,
      selected_instance_ids: ["f1", "f3"],
      action: "collective_pack",
      operator_ack: true,
    });
    expect(c.tray_ready).toBe(true);
    expect(c.selected_count).toBe(2);
    expect(c.pack_dispatched).toBe(false);
    expect(c.merge_executed).toBe(false);
    expect(c.live_dispatched).toBe(false);
    expect(c.authority).toBe("floating_instance_tray_compose_advisory");
    expect(formatFloatingInstanceTraySummary(c)).toMatch(/pack_dispatched=false/);
  });

  it("fullscreen one and full merge gates", () => {
    const fs = composeFloatingInstanceTray({
      parent_asset_id: "asset-1",
      members,
      selected_instance_ids: ["f2"],
      action: "fullscreen_one",
      operator_ack: false,
    });
    expect(fs.tray_ready).toBe(true);

    const fullNoAck = composeFloatingInstanceTray({
      parent_asset_id: "asset-1",
      members,
      selected_instance_ids: ["f1"],
      action: "full_merge_one",
      operator_ack: false,
    });
    expect(fullNoAck.tray_ready).toBe(false);

    const full = composeFloatingInstanceTray({
      parent_asset_id: "asset-1",
      members,
      selected_instance_ids: ["f1"],
      action: "full_merge_one",
      operator_ack: true,
    });
    expect(full.tray_ready).toBe(true);
    expect(full.merge_executed).toBe(false);
  });

  it("rejects cross-parent and unknown selection", () => {
    expect(() =>
      composeFloatingInstanceTray({
        parent_asset_id: "asset-1",
        members: [
          members[0],
          {
            instance_id: "x",
            parent_asset_id: "other",
            status: "open",
          },
        ],
        selected_instance_ids: [],
        action: "none",
        operator_ack: false,
      }),
    ).toThrow(/parent_asset_id/);
    expect(() =>
      composeFloatingInstanceTray({
        parent_asset_id: "asset-1",
        members,
        selected_instance_ids: ["missing"],
        action: "fullscreen_one",
        operator_ack: false,
      }),
    ).toThrow(/not in members/);
  });
});
