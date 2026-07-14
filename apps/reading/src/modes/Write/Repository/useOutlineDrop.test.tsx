import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { placeBlockMock } = vi.hoisted(() => ({ placeBlockMock: vi.fn() }));

vi.mock("../writeApi", async (orig) => ({
  ...(await orig<typeof import("../writeApi")>()),
  placeBlock: placeBlockMock,
}));

import { useOutlineDrop } from "./useOutlineDrop";

beforeEach(() => placeBlockMock.mockReset().mockResolvedValue("oblk-placed"));

describe("useOutlineDrop commit boundary", () => {
  it("does not report a committed placement as failed when onPlaced rejects", async () => {
    const onError = vi.fn();
    const onPlaced = vi.fn().mockRejectedValue(new Error("refresh offline"));
    const { result } = renderHook(() => useOutlineDrop({
      sectionId: "sec-1", onPlaced, onError,
    }));
    const event = {
      preventDefault: vi.fn(),
      dataTransfer: {
        getData: () => JSON.stringify({
          from: "palette", block_kind: "claim", block_id: "node-1", label: "Claim",
        }),
        types: ["application/x-antiek-block"],
      },
    } as unknown as React.DragEvent;
    act(() => result.current.onDrop(event));
    await act(async () => { await Promise.resolve(); await Promise.resolve(); });
    expect(placeBlockMock).toHaveBeenCalledTimes(1);
    expect(onPlaced).toHaveBeenCalledWith("oblk-placed");
    expect(onError).not.toHaveBeenCalled();
  });
});
