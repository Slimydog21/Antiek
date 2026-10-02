import { describe, expect, it } from "vitest";

import {
  buildCorrection,
  foldMemoryVersions,
  formatProvenance,
  parseSubstrateTimestamp,
  supersededLocally,
  type AccountMemoryItem,
} from "./accountMemory";

/**
 * Unit coverage for the pure half of the account-memory client.
 *
 * The behaviour that matters end to end — sign in, seed, render, correct, still
 * reach the superseded original — is proven against a REAL backend in
 * e2e/account-memory-panel.spec.ts, which is the task's done-bar. These tests
 * exist for the cases that round trip is a clumsy way to reach: an offset-less
 * timestamp, a duplicate edge arriving twice, a key whose head has been closed
 * by a writer this client never saw.
 */

function item(overrides: Partial<AccountMemoryItem> = {}): AccountMemoryItem {
  return {
    memory_id: "memory-1",
    edge_id: "edge-1",
    subject: "operator",
    predicate: "prefers",
    object: "footnotes",
    provenance: { source: "test" },
    valid_from: "2026-09-01T10:00:00",
    valid_to: null,
    superseded_by: null,
    ...overrides,
  };
}

describe("parseSubstrateTimestamp", () => {
  it("reads an offset-less substrate timestamp as UTC, not local time", () => {
    // The naive form the routes actually serialise. Read as local time this
    // would shift by the runner's zone; the assertion pins it to UTC.
    expect(parseSubstrateTimestamp("2026-09-01T10:00:00")?.toISOString()).toBe(
      "2026-09-01T10:00:00.000Z",
    );
  });

  it("leaves a value that already carries an offset alone", () => {
    expect(parseSubstrateTimestamp("2026-09-01T12:00:00+02:00")?.toISOString()).toBe(
      "2026-09-01T10:00:00.000Z",
    );
  });

  it("returns null rather than an Invalid Date", () => {
    expect(parseSubstrateTimestamp("not a timestamp")).toBeNull();
    expect(parseSubstrateTimestamp("")).toBeNull();
  });
});

describe("foldMemoryVersions", () => {
  it("groups by (subject, predicate), never by subject alone", () => {
    const groups = foldMemoryVersions([
      item({ edge_id: "a", predicate: "reads_at", object: "night" }),
      item({ edge_id: "b", predicate: "writes_in", object: "long form" }),
    ]);
    expect(groups).toHaveLength(2);
    expect(groups.every((group) => group.superseded.length === 0)).toBe(true);
  });

  it("keeps a superseded version under its head instead of dropping it", () => {
    const groups = foldMemoryVersions([
      item({
        edge_id: "old",
        object: "footnotes",
        valid_from: "2026-09-01T10:00:00",
        valid_to: "2026-09-05T10:00:00",
        superseded_by: "new",
      }),
      item({ edge_id: "new", object: "author-date", valid_from: "2026-09-05T10:00:00" }),
    ]);
    expect(groups).toHaveLength(1);
    expect(groups[0].head.edge_id).toBe("new");
    expect(groups[0].superseded.map((row) => row.edge_id)).toEqual(["old"]);
  });

  it("orders several superseded versions newest first", () => {
    const groups = foldMemoryVersions([
      item({ edge_id: "v1", valid_from: "2026-09-01T10:00:00", valid_to: "2026-09-02T10:00:00" }),
      item({ edge_id: "v2", valid_from: "2026-09-02T10:00:00", valid_to: "2026-09-03T10:00:00" }),
      item({ edge_id: "v3", valid_from: "2026-09-03T10:00:00" }),
    ]);
    expect(groups[0].head.edge_id).toBe("v3");
    expect(groups[0].superseded.map((row) => row.edge_id)).toEqual(["v2", "v1"]);
  });

  it("deduplicates by edge_id, so a retained row re-read from the server renders once", () => {
    const retained = item({ edge_id: "old", valid_to: "2026-09-05T10:00:00" });
    const groups = foldMemoryVersions([
      retained,
      { ...retained, object: "server copy" },
      item({ edge_id: "new", valid_from: "2026-09-05T10:00:00" }),
    ]);
    expect(groups[0].superseded).toHaveLength(1);
    // Last write wins: the server's copy of a row beats the local one.
    expect(groups[0].superseded[0].object).toBe("server copy");
  });

  it("still renders a key whose every version is closed", () => {
    // A writer this client never saw can close a head between two reads. The
    // fact must not disappear from the page because of it.
    const groups = foldMemoryVersions([
      item({ edge_id: "closed", valid_from: "2026-09-01T10:00:00", valid_to: "2026-09-02T10:00:00" }),
    ]);
    expect(groups).toHaveLength(1);
    expect(groups[0].head.edge_id).toBe("closed");
    expect(groups[0].superseded).toEqual([]);
  });

  it("orders groups newest head first, with a total tie-break", () => {
    const groups = foldMemoryVersions([
      item({ edge_id: "a", predicate: "one", valid_from: "2026-09-01T10:00:00" }),
      item({ edge_id: "b", predicate: "two", valid_from: "2026-09-03T10:00:00" }),
      item({ edge_id: "c", predicate: "three", valid_from: "2026-09-03T10:00:00" }),
    ]);
    expect(groups.map((group) => group.predicate)).toEqual(["three", "two", "one"]);
  });
});

describe("supersededLocally", () => {
  it("stamps the closed row with the interval the substrate actually wrote", () => {
    const previous = item({ edge_id: "old" });
    const replacement = item({
      edge_id: "new",
      memory_id: "memory-2",
      valid_from: "2026-09-05T10:00:00",
    });
    const closed = supersededLocally(previous, replacement);
    // write_memory_item sets valid_until to the REPLACEMENT's valid_from and
    // superseded_by to the replacement's EDGE id — not its memory id.
    expect(closed.valid_to).toBe("2026-09-05T10:00:00");
    expect(closed.superseded_by).toBe("new");
    expect(closed.object).toBe(previous.object);
  });

  it("refuses to close a row belonging to a different fact", () => {
    const previous = item({ edge_id: "old", predicate: "reads_at" });
    const unrelated = item({ edge_id: "new", predicate: "writes_in" });
    expect(supersededLocally(previous, unrelated)).toBe(previous);
  });
});

describe("formatProvenance", () => {
  it("sorts keys so the same provenance always reads the same way", () => {
    expect(formatProvenance({ source: "doc_ingest", authority: "cookie" })).toBe(
      "authority=cookie · source=doc_ingest",
    );
  });

  it("encodes a non-string value rather than showing [object Object]", () => {
    expect(formatProvenance({ nested: { a: 1 } })).toBe('nested={"a":1}');
  });

  it("says so when there is nothing to show", () => {
    expect(formatProvenance({})).toBe("no provenance recorded");
  });
});

describe("buildCorrection", () => {
  it("carries the corrected fact's identity in provenance", () => {
    const head = item({ memory_id: "memory-7", edge_id: "edge-7" });
    const write = buildCorrection(head, "  author-date  ", {
      now: new Date("2026-09-05T10:00:00Z"),
      note: "  house style changed  ",
    });
    expect(write).toEqual({
      subject: "operator",
      predicate: "prefers",
      object: "author-date",
      provenance: {
        source: "account_memory_panel",
        corrects_memory_id: "memory-7",
        corrects_edge_id: "edge-7",
        note: "house style changed",
      },
      valid_from: "2026-09-05T10:00:00.000Z",
    });
  });

  it("omits an empty note rather than writing a blank one", () => {
    const write = buildCorrection(item(), "author-date", {
      now: new Date("2026-09-05T10:00:00Z"),
      note: "   ",
    });
    expect(write.provenance).not.toHaveProperty("note");
  });

  it("never sends a server-owned authority field", () => {
    const write = buildCorrection(item(), "author-date", { now: new Date() });
    expect(
      Object.keys(write.provenance).some((key) => key.toLowerCase().startsWith("authority_")),
    ).toBe(false);
  });
});
