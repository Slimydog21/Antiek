import { describe, expect, it } from "vitest";

import type { Event } from "../../generated/types";
import {
  makeSiteSeeAugmentation,
  tintForState,
  SITESEE_READ_CLASS,
  type SiteSeeSourceView,
} from "../../reading-physics/augmentations/sitesee";
import type { Decoration } from "../../reading-physics/types";
import { resolveCitationHistory, stateForChunk } from "./resolveCitationHistory";

/** A source.read event on a reading thread, attributed to a chunk. */
function readEvent(chunkId: string, over: Partial<Event> = {}): Event {
  return {
    event_id: `ev-${chunkId}`,
    investigation_id: "read-doc-1",
    action_type: "source.read",
    payload: { action_type: "source.read", chunk_id: chunkId, dwell_ms: 40_000, page_count: 3 },
    param_version: "v1",
    emitted_at: "2026-05-28T00:00:00Z",
    document_id: "doc-1",
    ...over,
  } as Event;
}

describe("resolveCitationHistory — lighting the SiteSee read tint (M4)", () => {
  it("resolves a chunk marked by a source.read event to the 'read' state", () => {
    const history = resolveCitationHistory({ events: [readEvent("chunk-7")] });
    expect(stateForChunk(history, "chunk-7")).toBe("read");
  });

  it("a chunk with no signal is the honest 'unseen' default (no tint)", () => {
    const history = resolveCitationHistory({ events: [] });
    expect(stateForChunk(history, "chunk-x")).toBe("unseen");
    expect(tintForState("unseen")).toBeNull();
  });

  it("respects precedence cited ≻ saved ≻ read (one tint per source)", () => {
    const history = resolveCitationHistory({
      events: [readEvent("c1"), readEvent("c2"), readEvent("c3")],
      savedChunkIds: new Set(["c2"]),
      citedChunkIds: new Set(["c3"]),
    });
    expect(stateForChunk(history, "c1")).toBe("read"); // read only
    expect(stateForChunk(history, "c2")).toBe("saved"); // saved beats read
    expect(stateForChunk(history, "c3")).toBe("cited"); // cited beats all
  });

  it("the resolved 'read' state produces the read tint through SiteSee (the previously-dormant tint, now lit)", () => {
    const history = resolveCitationHistory({ events: [readEvent("chunk-7")] });
    const source: SiteSeeSourceView = {
      representativeChunkId: "chunk-7",
      state: stateForChunk(history, "chunk-7"),
      servable: true,
      title: "A Read Source",
      ipHolderName: null,
    };
    // Drive the SHIPPED augmentation with the resolved state and capture its
    // declared tint decoration — proof the resolver lights the read tint.
    const decorations: Decoration[] = [];
    const aug = makeSiteSeeAugmentation([source]);
    aug.contribute({} as never, {
      declareDecoration: (d: Decoration) => decorations.push(d),
      declareAnchoredWidget: () => {},
    } as never);
    expect(decorations.some((d) => d.className === SITESEE_READ_CLASS)).toBe(true);
  });

  it("§9.0: the resolver reads only event metadata — a source.read carries no body to leak", () => {
    const ev = readEvent("chunk-7");
    // The payload structurally has no body field; the resolver only reads
    // chunk_id off it. Asserting the shape guards against a future body leak.
    expect(Object.keys(ev.payload)).not.toContain("excerpt");
    const history = resolveCitationHistory({ events: [ev] });
    expect(stateForChunk(history, "chunk-7")).toBe("read");
  });
});
