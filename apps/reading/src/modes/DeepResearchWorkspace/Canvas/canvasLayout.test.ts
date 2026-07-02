import { describe, expect, it } from "vitest";

import type { Event } from "../../../generated/types";
import { replayPositions } from "./canvasLayout";

function positionEvent(
  id: string,
  payload: Record<string, unknown>,
  emittedAt = "2026-07-01T12:00:00Z",
): Event {
  return {
    event_id: id,
    investigation_id: "inv-1",
    action_type: "block.positioned" as Event["action_type"],
    payload: {
      action_type: "block.positioned",
      ...payload,
    } as Event["payload"],
    param_version: "test",
    emitted_at: emittedAt,
  };
}

describe("canvasLayout replayPositions", () => {
  it("drops malformed block.positioned payloads instead of minting unsafe coordinates", () => {
    const positions = replayPositions([
      positionEvent("valid", { node_id: "i1", x: 120, y: 80 }),
      positionEvent("nan-x", { node_id: "i1", x: Number.NaN, y: 999 }, "2026-07-01T12:00:01Z"),
      positionEvent("bad-node", { node_id: "", x: 240, y: 120 }, "2026-07-01T12:00:02Z"),
      positionEvent(
        "bad-region",
        { node_id: "i2", x: 300, y: 140, region_id: 42 },
        "2026-07-01T12:00:03Z",
      ),
      positionEvent("valid-later", { node_id: "i1", x: 180, y: 100 }, "2026-07-01T12:00:04Z"),
    ]);

    expect([...positions.keys()]).toEqual(["i1"]);
    expect(positions.get("i1")).toMatchObject({
      x: 180,
      y: 100,
      regionId: null,
      regionLabel: null,
      persisted: true,
    });
  });
});
