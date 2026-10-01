/**
 * Servability parity: the frontend union must accept every value the backend
 * can emit, and every consumer must render it (FFX SPR-02, finding A-01).
 *
 * A-01: the backend added `personal_readable` (substrate/books/servability.py,
 * substrate/constants.py) and the frontend `Servability` union did not, so
 * `servabilityLabel` fell off its switch, returned `undefined`, and the reader
 * crashed destructuring `label` from it. This test reads the backend source at
 * test time, so the next enum drift fails in CI instead of in a user's reader.
 *
 * Extraction (both regexes run on text with `#` comments and triple-quoted
 * docstrings already stripped, so a commented-out or documented value is not
 * counted):
 *   - servability.py: the body of `class ServabilityStatus(...)`, i.e. every
 *     indented line after the class header up to the next top-level line.
 *     Members are `NAME = 'value'` or `NAME = "value"` lines at the body's
 *     own indentation (that of its first non-blank line), so assignments in a
 *     nested block (a helper method) are not counted.
 *   - constants.py: the parenthesised tuple after
 *     `BOOK_SERVABILITY_STATUSES: Final[tuple[str, ...]] = (` up to the first
 *     line that is exactly `)`; values are single- or double-quoted literals.
 * The two backend sources must agree with each other as well as with us.
 *
 * Known under-matches (review R-03). Each drops a value silently, so a
 * backend edit into one of these shapes would escape this test:
 *   - a `#` inside a value string (stripped as a comment), in the enum or tuple;
 *   - a value outside [a-z0-9_] ("PublicDomain", "public-domain");
 *   - a prefixed literal (r"value", f"value", b"value");
 *   - enum members indented differently from the body's first line (mixed
 *     tabs and spaces).
 * None occurs in today's servability.py or constants.py. The cross-check that
 * the enum and tuple extractions agree, and the >= 6 values floor, catch a
 * drop in only one of the two files but not the same drop in both.
 */
import { existsSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

import {
  isServability,
  SERVABILITY_VALUES,
  servabilityLabel,
  UNKNOWN_RIGHTS_LABEL,
  type Servability,
} from "./books";

// apps/reading/src/api -> repo root. The monorepo layout is fixed. (jsdom's
// global URL rejects `new URL(rel, import.meta.url)` for fileURLToPath, so
// resolve the path with node:path as design/token-parity.test.ts does.)
const here = dirname(fileURLToPath(import.meta.url));
const SERVABILITY_PY = resolve(here, "../../../../substrate/books/servability.py");
const CONSTANTS_PY = resolve(here, "../../../../substrate/constants.py");

/** Remove `#` comments and triple-quoted strings. Good enough for these two
 * files: neither contains a `#` inside a string literal on a member line. */
function stripPythonNoise(src: string): string {
  return src
    .replace(/"""[\s\S]*?"""/g, "")
    .replace(/'''[\s\S]*?'''/g, "")
    .replace(/#[^\n]*/g, "");
}

function extractEnumValues(servabilityPy: string): string[] {
  const src = stripPythonNoise(servabilityPy);
  const header = /^class ServabilityStatus\([^)]*\):[^\n]*\n/m.exec(src);
  if (!header) return [];
  const rest = src.slice(header.index + header[0].length);
  // The class body ends at the first non-blank line with no indentation.
  const end = /^\S/m.exec(rest);
  const body = end ? rest.slice(0, end.index) : rest;
  // Member indentation = the first non-blank body line's leading whitespace.
  const indent = /^([ \t]+)\S/m.exec(body)?.[1];
  if (!indent) return [];
  const member = new RegExp(`^${indent}[A-Z][A-Z0-9_]*\\s*=\\s*(["'])([a-z0-9_]+)\\1`, "gm");
  return [...body.matchAll(member)].map((m) => m[2]);
}

function extractTupleValues(constantsPy: string): string[] {
  const src = stripPythonNoise(constantsPy);
  const start = /^BOOK_SERVABILITY_STATUSES\s*:[^=]*=\s*\(/m.exec(src);
  if (!start) return [];
  const rest = src.slice(start.index + start[0].length);
  const end = /^\)/m.exec(rest);
  const body = end ? rest.slice(0, end.index) : rest;
  return [...body.matchAll(/(["'])([a-z0-9_]+)\1/g)].map((m) => m[2]);
}

describe("servability extraction (fixture cases; known under-matches listed in the header)", () => {
  it("ignores commented-out members and docstring mentions, and stops at the class end", () => {
    const fixture = [
      "class ServabilityStatus(StrEnum):",
      '    """Docs mention RETIRED = "retired_value" in prose."""',
      "",
      '    PUBLIC_DOMAIN = "public_domain"',
      '    # OLD_VALUE = "old_value"',
      '    NEW_VALUE = "new_value"  # trailing comment',
      "",
      "",
      "_OTHER = {",
      '    FAKE = "not_a_member"',
      "}",
    ].join("\n");
    expect(extractEnumValues(fixture)).toEqual(["public_domain", "new_value"]);
  });

  it("accepts single-quoted members as well as double-quoted ones (F-05)", () => {
    const fixture = [
      "class ServabilityStatus(StrEnum):",
      "    PUBLIC_DOMAIN = 'public_domain'",
      '    PERSONAL_READABLE = "personal_readable"',
      "",
      "_X = 1",
    ].join("\n");
    expect(extractEnumValues(fixture)).toEqual(["public_domain", "personal_readable"]);
    const tuple = [
      "BOOK_SERVABILITY_STATUSES: Final[tuple[str, ...]] = (",
      "    'public_domain',",
      '    "personal_readable",',
      ")",
    ].join("\n");
    expect(extractTupleValues(tuple)).toEqual(["public_domain", "personal_readable"]);
  });

  it("counts only lines at the enum's own member indentation, not nested blocks (F-06)", () => {
    const fixture = [
      "class ServabilityStatus(StrEnum):",
      '    PUBLIC_DOMAIN = "public_domain"',
      "",
      "    @classmethod",
      "    def _inner(cls):",
      '        INNER = "inner_value"',
      "        return INNER",
      "",
      '    REAL_VALUE = "real_value"',
      "",
      "def after():",
      '    OUTSIDE = "outside_value"',
    ].join("\n");
    expect(extractEnumValues(fixture)).toEqual(["public_domain", "real_value"]);
  });

  it("reads only the tuple body and skips commented values", () => {
    const fixture = [
      "BOOK_SERVABILITY_STATUSES: Final[tuple[str, ...]] = (",
      '    "public_domain",  # "not_this"',
      '    # "commented_out",',
      '    "personal_readable",',
      ")",
      'BOOK_DEFAULT_SERVABILITY: Final[str] = "gated_metadata_only"',
    ].join("\n");
    expect(extractTupleValues(fixture)).toEqual(["public_domain", "personal_readable"]);
  });
});

describe("private-authored presentation contract", () => {
  it("accepts the eight canonical statuses and rejects the upload-attestation alias", () => {
    expect([...SERVABILITY_VALUES].sort()).toEqual([
      "public_domain", "platform_authored", "publisher_opted_in", "source_declared_open",
      "gated_metadata_only", "taken_down", "personal_readable", "private_authored",
    ].sort());
    expect(isServability("private_authored")).toBe(true);
    expect(isServability("user_authored_private")).toBe(false);
    expect(servabilityLabel("private_authored")).toEqual({ label: "Private authored", colour: "muted" });
  });
});

const backendPresent = existsSync(SERVABILITY_PY) && existsSync(CONSTANTS_PY);

describe.skipIf(!backendPresent)(
  `servability parity with the backend enum${backendPresent ? "" : " (SKIPPED: backend sources not found at " + SERVABILITY_PY + " / " + CONSTANTS_PY + "; parity is unchecked in this checkout)"}`,
  () => {
    const enumValues = backendPresent ? extractEnumValues(readFileSync(SERVABILITY_PY, "utf8")) : [];
    const tupleValues = backendPresent ? extractTupleValues(readFileSync(CONSTANTS_PY, "utf8")) : [];

    it("extracted a non-trivial, self-consistent backend vocabulary", () => {
      // Guards against the test going vacuous if the backend source moves.
      expect(enumValues.length).toBeGreaterThanOrEqual(6);
      expect([...enumValues].sort()).toEqual([...tupleValues].sort());
    });

    it.each(enumValues)("isServability accepts backend value %s", (value) => {
      expect(isServability(value)).toBe(true);
    });

    it.each(enumValues)("servabilityLabel renders backend value %s", (value) => {
      const result = servabilityLabel(value as Servability);
      expect(result, `servabilityLabel(${JSON.stringify(value)}) returned no label`).toBeDefined();
      expect(result.label.trim().length).toBeGreaterThan(0);
      // A backend value must have its own copy, not the runtime fallback.
      expect(result.label).not.toBe(UNKNOWN_RIGHTS_LABEL);
    });
  },
);

describe("servabilityLabel is total at runtime", () => {
  it("renders a neutral badge for a value this build does not know", () => {
    expect(servabilityLabel("from_a_newer_backend" as Servability)).toEqual({
      label: UNKNOWN_RIGHTS_LABEL,
      colour: "muted",
    });
    expect(isServability("from_a_newer_backend")).toBe(false);
    expect(isServability(null)).toBe(false);
  });

  it("never calls a personal document an Antiek original or a library title (A-06 copy half)", () => {
    const { label, colour } = servabilityLabel("personal_readable");
    expect(label).toBe("Personal reading");
    expect(colour).toBe("muted");
    expect(label).not.toMatch(/original|library/i);
  });

  it("leaves platform_authored copy unchanged (real platform titles use it)", () => {
    expect(servabilityLabel("platform_authored").label).toBe("Antiek original");
  });
});
