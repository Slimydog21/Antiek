import { describe, expect, it } from "vitest";

import {
  MAX_OUTLINE_SECTIONS,
  prepareHtmlDraftForWrite,
  splitHtmlIntoOutlineSections,
  stripHtmlToPlainText,
  titleHintFromDraft,
} from "./htmlDraftImport";

describe("htmlDraftImport residual fm/fu", () => {
  it("strips tags and scripts to plain text", () => {
    const plain = stripHtmlToPlainText(
      "<p>Hello <b>world</b></p><script>alert(1)</script><style>.x{}</style>",
    );
    expect(plain).toBe("Hello world");
  });

  it("titleHint prefers API title then plain text then document id", () => {
    expect(
      titleHintFromDraft({ title: "  Merged research  ", plain_text: "ignored" }),
    ).toBe("Merged research");
    expect(
      titleHintFromDraft({
        title: "",
        plain_text: "First sentence. Second.",
        document_id: "d1",
      }),
    ).toBe("First sentence.");
    expect(titleHintFromDraft({ document_id: "draft_abc" })).toMatch(/draft_abc/);
  });

  it("prepareHtmlDraftForWrite requires html view_format and body", () => {
    expect(() =>
      prepareHtmlDraftForWrite({
        document_id: "d1",
        view_format: "pdf",
        html: "%PDF",
      }),
    ).toThrow(/html/i);
    expect(() =>
      prepareHtmlDraftForWrite({
        document_id: "d1",
        view_format: "html",
        html: "   ",
      }),
    ).toThrow(/empty/i);
    const out = prepareHtmlDraftForWrite({
      document_id: "draft_1",
      view_format: "html",
      title: "Analysis",
      html: "<article><h1>Hi</h1><p>Body text here.</p></article>",
    });
    expect(out.view_format).toBe("html");
    expect(out.title).toBe("Analysis");
    expect(out.plain_text).toMatch(/Body text here/);
    expect(out.plain_preview.length).toBeGreaterThan(5);
    expect(out.outline_sections.length).toBeGreaterThanOrEqual(1);
  });

  it("splitHtmlIntoOutlineSections uses single section when no headings (fu)", () => {
    const secs = splitHtmlIntoOutlineSections(
      "<p>Only a paragraph of research.</p>",
      "Fallback Title",
    );
    expect(secs).toHaveLength(1);
    expect(secs[0].title).toBe("Fallback Title");
    expect(secs[0].plain_text).toMatch(/Only a paragraph/);
    expect(secs[0].section_index).toBe(0);
  });

  it("splitHtmlIntoOutlineSections splits on h1/h2 with preamble (fu)", () => {
    const html = `
      <p>Preamble before headings.</p>
      <h1>First</h1>
      <p>Body one.</p>
      <h2>Second</h2>
      <p>Body two more text.</p>
    `;
    const secs = splitHtmlIntoOutlineSections(html, "Draft");
    expect(secs.length).toBe(3);
    expect(secs[0].title).toMatch(/Draft|Introduction/);
    expect(secs[0].plain_text).toMatch(/Preamble/);
    expect(secs[1].title).toBe("First");
    expect(secs[1].plain_text).toMatch(/Body one/);
    expect(secs[2].title).toBe("Second");
    expect(secs[2].plain_text).toMatch(/Body two/);
    expect(secs.map((s) => s.section_index)).toEqual([0, 1, 2]);
  });

  it("splitHtmlIntoOutlineSections caps at MAX_OUTLINE_SECTIONS (fu)", () => {
    let html = "";
    for (let i = 0; i < MAX_OUTLINE_SECTIONS + 5; i++) {
      html += `<h2>Sec ${i}</h2><p>Body ${i}</p>`;
    }
    const secs = splitHtmlIntoOutlineSections(html, "Cap");
    expect(secs.length).toBe(MAX_OUTLINE_SECTIONS);
    expect(secs[secs.length - 1].section_index).toBe(MAX_OUTLINE_SECTIONS - 1);
  });

  it("splitHtmlIntoOutlineSections records heading_level for nesting (fv)", () => {
    const secs = splitHtmlIntoOutlineSections(
      "<h1>Top</h1><p>A</p><h2>Sub</h2><p>B</p><h3>Deep</h3><p>C</p>",
      "Doc",
    );
    expect(secs.map((s) => s.heading_level)).toEqual([1, 2, 3]);
    expect(secs.map((s) => s.title)).toEqual(["Top", "Sub", "Deep"]);
  });

  it("splitHtmlIntoOutlineSections keeps html_fragment for HTML-first prose (fx)", () => {
    const secs = splitHtmlIntoOutlineSections(
      "<h1>One</h1><p>Alpha <em>rich</em>.</p><h2>Two</h2><p>Beta.</p>",
      "Doc",
    );
    expect(secs[0].html_fragment).toMatch(/<p>Alpha <em>rich<\/em>\.<\/p>/i);
    expect(secs[0].plain_text).toMatch(/Alpha rich/);
    expect(secs[1].html_fragment).toMatch(/Beta/);
  });
});
