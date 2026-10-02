import { describe, expect, it } from "vitest";
import { DEFAULT_READING_TYPOGRAPHY, parseReadingTypography, readingTypographyStyle } from "./readingTypography";

describe("reading typography boundary", () => {
  it.each([null, "Source Sans 3", [], {}, { version: 2, font: "source-sans" }])("uses a readable default for unsupported data %j", (value) => {
    expect(parseReadingTypography(value)).toEqual(DEFAULT_READING_TYPOGRAPHY);
  });

  it("rejects injected font names and keeps valid independent preferences", () => {
    expect(parseReadingTypography({ version: 1, font: 'url("https://example.invalid")', size: 22, lineHeight: 1.8, measure: 78, letterSpacing: 0.03 })).toEqual({
      font: "source-serif", size: 22, lineHeight: 1.8, measure: 78, letterSpacing: 0.03,
    });
  });

  it("bounds numeric settings and rejects invalid or unsupported choices", () => {
    expect(parseReadingTypography({ version: 1, size: 900, lineHeight: -1, measure: 0, letterSpacing: 1 })).toEqual({
      font: "source-serif", size: 32, lineHeight: 1.4, measure: 66, letterSpacing: 0,
    });
    expect(parseReadingTypography({ version: 1, size: NaN, lineHeight: Infinity, measure: "78" })).toEqual(DEFAULT_READING_TYPOGRAPHY);
  });

  it("uses rem so reader sizing follows browser text-size preferences", () => {
    const style = readingTypographyStyle({ ...DEFAULT_READING_TYPOGRAPHY, size: 24 });
    expect(style.fontSize).toBe("1.5rem");
    expect(style.maxWidth).toBe("66ch");
    expect(style.fontFamily).toContain('"Source Serif 4"');
  });
});
