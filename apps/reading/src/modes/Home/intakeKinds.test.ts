/**
 * intakeKinds.test.ts — FFX-KPA SPR-03 M3: one table decides what the zen
 * home's drop zone accepts. Text kinds and URLs reach their existing routes;
 * images, PDFs and documents are refused (and never uploaded) until SPR-B's
 * intake contract (ffx-nav-backend-intake) is live.
 */
import { describe, expect, it } from "vitest";

import {
  INTAKE_CONTRACT,
  INTAKE_KINDS,
  MAX_ATTACHMENTS,
  REFUSED_UNTIL_INTAKE_COPY,
  acceptanceFor,
  classifyFile,
  classifyText,
} from "./intakeKinds";

const file = (name: string, type: string) => new File(["x"], name, { type });

describe("intakeKinds — classification", () => {
  it.each([
    ["notes.md", "", "text-file"],
    ["data.csv", "text/csv", "text-file"],
    ["anything", "text/plain", "text-file"],
    ["photo.png", "image/png", "image"],
    ["scan.JPG", "", "image"],
    ["paper.pdf", "application/pdf", "pdf"],
    ["draft.docx", "", "docx"],
    ["blob.bin", "application/octet-stream", "unsupported"],
  ] as const)("%s (%s) → %s", (name, type, kind) => {
    expect(classifyFile(file(name, type))).toBe(kind);
  });

  it.each([
    ["photo.png", "text/plain", "image"],
    ["paper.pdf", "text/plain", "pdf"],
    ["draft.docx", "text/plain", "docx"],
    ["notes.txt", "image/png", "image"],
    ["notes.txt", "application/pdf", "pdf"],
  ] as const)("a refused kind wins over text: %s (%s) → %s", (name, type, kind) => {
    expect(classifyFile(file(name, type))).toBe(kind);
  });

  it("a bare http(s) URL is a url; anything else is not", () => {
    expect(classifyText("https://example.org/a")).toBe("url");
    expect(classifyText("  http://x.y/z  ")).toBe("url");
    expect(classifyText("see https://example.org")).toBeNull();
  });
});

describe("intakeKinds — acceptance", () => {
  it("text files and URLs route to the existing ingest endpoints", () => {
    expect(acceptanceFor("text-file")).toEqual({ accepted: true, route: "POST /voice-notes/ingest" });
    expect(acceptanceFor("url")).toEqual({ accepted: true, route: "POST /sources/ingest" });
  });

  it("image / pdf / docx are refused with the exact copy while the contract is off", () => {
    expect(INTAKE_CONTRACT.live).toBe(false);
    for (const kind of ["image", "pdf", "docx"] as const) {
      expect(acceptanceFor(kind)).toEqual({ accepted: false, copy: REFUSED_UNTIL_INTAKE_COPY });
    }
    expect(REFUSED_UNTIL_INTAKE_COPY).toBe(
      "Images and documents arrive once the intake lands; paste the text for now.",
    );
  });

  it("a live contract without a published route still refuses (no guessed endpoint)", () => {
    expect(acceptanceFor("image", { live: true, route: null })).toMatchObject({ accepted: false });
    expect(acceptanceFor("pdf", { live: true, route: "POST /intake/seed" })).toEqual({
      accepted: true,
      route: "POST /intake/seed",
    });
  });

  it("every kind has exactly one table row and the cap is the inherited six", () => {
    const kinds = INTAKE_KINDS.map((row) => row.kind);
    expect(new Set(kinds).size).toBe(kinds.length);
    expect(kinds.sort()).toEqual(["docx", "image", "pdf", "text-file", "unsupported", "url"]);
    expect(MAX_ATTACHMENTS).toBe(6);
  });
});
