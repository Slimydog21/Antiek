/**
 * frameContract.test.ts — SPR-07 M1/M4 drift guard.
 *
 * The TS telemetry contract (frameContract.ts) is hand-written because the
 * SPR-05 codegen (tools/codegen/emit_contracts.py) emits ONLY the accrual
 * OUTPUT shape into src/generated/contracts.ts — it does not emit the
 * telemetry INPUT shapes (WindowFrameBatch / FrameSecond / FrameAttentionSample).
 * So nothing mechanically keeps the hand-written mirror aligned with the Python
 * source of truth, substrate/ad_inventory/frame_attention.py.
 *
 * This test IS the alignment. It pins the exact field set of each interface and
 * the stamped schema-version string against the values read out of
 * frame_attention.py at SPR-07 (file:line cited per field). If the Python
 * contract changes a field name, adds a field, or bumps the version, this test
 * is the thing that must be updated in lock-step — the divergence cannot pass
 * silently. The field lists below were verified against:
 *
 *   FRAME_TELEMETRY_SCHEMA_VERSION  frame_attention.py:117  = "frame-telemetry-v1"
 *   VALID_LENSES                    frame_attention.py:151  = {read,research,write,speak}
 *   FrameAttentionSample            frame_attention.py:185-190
 *   FrameSecond                     frame_attention.py:215-217
 *   WindowFrameBatch                frame_attention.py:242-245
 *
 * TS interfaces are erased at runtime, so the pin is enforced via a typed
 * builder: each `satisfies` forces the object to carry EXACTLY the contract
 * fields (an added/removed/renamed field reddens at `tsc`), and the runtime
 * assertions pin the version string + lens vocabulary + the field KEYS of a
 * fully-populated instance (so an optional field silently dropped from the
 * interface is still caught at runtime).
 */
import { describe, expect, it } from "vitest";

import {
  FRAME_TELEMETRY_SCHEMA_VERSION,
  VALID_LENSES,
  type FrameAttentionSample,
  type FrameSecond,
  type WindowFrameBatch,
} from "./frameContract";

describe("frameContract — pins the TS mirror against frame_attention.py", () => {
  it("stamps the exact Python FRAME_TELEMETRY_SCHEMA_VERSION", () => {
    // frame_attention.py — FRAME_TELEMETRY_SCHEMA_VERSION = "frame-telemetry-v2"
    // (AFA-S1 bumped v1->v2 when ad_value_usd_cents left the client wire shape).
    expect(FRAME_TELEMETRY_SCHEMA_VERSION).toBe("frame-telemetry-v2");
  });

  it("mirrors the four VALID_LENSES exactly (frame_attention.py:151)", () => {
    expect([...VALID_LENSES].sort()).toEqual(["read", "research", "speak", "write"]);
  });

  it("FrameAttentionSample carries exactly the Python fields (frame_attention.py:185-190)", () => {
    // A fully-populated sample — every contract field present, including the
    // two optionals. `satisfies` forces the TS interface to match field-for-
    // field; the key assertion catches a field silently dropped at runtime.
    const sample = {
      asset_id: "doc-1",
      viewport_area_fraction: 0.5,
      prominence: 0.5,
      focused_dwell_ms: 1000,
      content_class: null,
      chunk_id: null,
    } satisfies FrameAttentionSample;
    expect(Object.keys(sample).sort()).toEqual(
      [
        "asset_id",
        "chunk_id",
        "content_class",
        "focused_dwell_ms",
        "prominence",
        "viewport_area_fraction",
      ].sort(),
    );
  });

  it("FrameSecond carries exactly the Python fields (frame_attention.py:215-217)", () => {
    const second = {
      second_index: 0,
      lens: "read",
      samples: [],
    } satisfies FrameSecond;
    expect(Object.keys(second).sort()).toEqual(
      ["lens", "samples", "second_index"].sort(),
    );
  });

  it("WindowFrameBatch carries exactly the CLIENT-INBOUND Python fields (v2: no value)", () => {
    // AFA-S1 (frame-telemetry-v2): ad_value_usd_cents is REMOVED from the
    // client mirror — the server prices the window, the client never does.
    // The Python server-side dataclass keeps the field (server-populated); the
    // inbound WindowFrameBatchIn (ad_routes.py) drops it, and this is that
    // inbound shape.
    const batch = {
      window_id: "win:read:abc",
      seconds: [],
      schema_version: FRAME_TELEMETRY_SCHEMA_VERSION,
    } satisfies WindowFrameBatch;
    expect(Object.keys(batch).sort()).toEqual(
      ["schema_version", "seconds", "window_id"].sort(),
    );
  });
});
