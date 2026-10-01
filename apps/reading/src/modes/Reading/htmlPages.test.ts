import { describe, expect, it } from "vitest";
import { paginateHtml, readerToc } from "./htmlPages";
import { paginate } from "./paginate";
import richBody from "./__fixtures__/passive_html_rich_body.json";

function htmlPages(html: string, splitHeadings = true) {
  const result = paginateHtml(html, splitHeadings);
  expect(result.kind).toBe("ready");
  return result.pages;
}

describe("passive HTML section windows", () => {
  it("accepts the rich-body output of the existing pinned server sanitizer", () => {
    const pages = htmlPages(richBody.served_html);
    expect(pages.map((page) => page.headingTitle)).toEqual(["Opening", "Evidence"]);
    expect(pages[0].text).toContain('start="3"');
    expect(pages[1].text).toContain('rowspan="2"');
    expect(pages[1].text).toContain('alt="Image description"');
    expect(pages[1].text).not.toContain('src=');
  });
  it("keeps the preamble, nested wrappers, tables and notes at their real heading windows", () => {
    const pages = htmlPages('<article id="book"><p>Preface 🌍 e\u0301.</p><h1 id="opening">Opening</h1><p>First.</p><section><h2 id="evidence">Evidence</h2><table><tr><td>42</td></tr></table><blockquote><p>Note.</p></blockquote></section><h3 id="last">Last</h3></article>');
    expect(pages).toHaveLength(3);
    expect(pages.map((page) => page.headingTitle)).toEqual(["Opening", "Evidence", "Last"]);
    expect(pages[0].text).toContain("Preface 🌍 e\u0301.");
    expect(pages[0].fragmentIds).toEqual(["book", "opening"]);
    expect(pages[1].fragmentIds).toEqual(["evidence"]);
    expect(pages[1].text).not.toContain('id="book"');
    const mounted = document.createElement("div");
    mounted.innerHTML = pages[1].text;
    expect(mounted.querySelector("tbody td")?.textContent).toBe("42");
    expect(mounted.querySelector("blockquote p")?.textContent).toBe("Note.");
    expect(mounted.querySelector("h2")?.id).toBe("evidence");
    expect(pages.every((page) => !("bodyStart" in page))).toBe(true);
  });

  it("assigns wrapped section destinations to the page containing their first content", () => {
    const pages = htmlPages('<h1>First</h1><p><a href="#s">Go</a></p><section id="s">\n<h2>Evidence</h2><p>42</p></section><article id="t"><div id="nested"><h3>Conclusion</h3><p>Done.</p></div></article>');
    expect(pages.map((page) => page.fragmentIds)).toEqual([[], ["s"], ["t", "nested"]]);
    const first = document.createElement("div");
    first.innerHTML = pages[0].text;
    expect(first.querySelector("#s, #t, #nested")).toBeNull();
    const evidence = document.createElement("div");
    evidence.innerHTML = pages[1].text;
    expect(evidence.querySelector("#s h2")?.textContent).toBe("Evidence");
    expect(evidence.querySelector("#s p")?.textContent).toBe("42");
    const conclusion = document.createElement("div");
    conclusion.innerHTML = pages[2].text;
    expect(conclusion.querySelector("#t #nested h3")?.textContent).toBe("Conclusion");
  });

  it("preserves wrapper preambles and original empty named anchors on their real window", () => {
    const pages = htmlPages('<h1>First</h1><section id="intro"><p>Introduction.</p><span id="empty"></span><h2>Evidence</h2><p>42</p></section>');
    expect(pages.map((page) => page.fragmentIds)).toEqual([["intro", "empty"], []]);
    const first = document.createElement("div");
    first.innerHTML = pages[0].text;
    expect(first.querySelector("#intro p")?.textContent).toBe("Introduction.");
    expect(first.querySelector("#empty")?.textContent).toBe("");
    expect(pages[1].text).not.toContain('id="intro"');
    expect(pages[1].text).not.toContain('id="empty"');
  });

  it("keeps visible leaf content and preformatted whitespace before a nested heading", () => {
    const pages = htmlPages('<h1>First</h1><section id="rule"><hr><h2>Second</h2></section><section id="space"><pre>  \n </pre><h3>Third</h3></section>');
    expect(pages.map((page) => page.fragmentIds)).toEqual([["rule"], ["space"], []]);
  });

  it("keeps heading-free safe HTML byte-for-byte, including preformatted spaces", () => {
    const source = '  <dl><dt>Term</dt><dd>Value</dd></dl><pre>  x\n y</pre><figure><img alt="No automatic image fetch"><figcaption>Caption</figcaption></figure>  ';
    const pages = htmlPages(source);
    expect(pages).toHaveLength(1);
    expect(pages[0].text).toBe(source);
    expect(pages[0].headingTitle).toBeNull();
    expect(paginateHtml("   ").pages).toEqual([]);
  });

  it("does not paginate an HTML body under a non-section server scheme", () => {
    const source = '<h1>First</h1><h2>Second</h2>';
    expect(htmlPages(source, false)[0].text).toBe(source);
    expect(htmlPages(source, false)).toHaveLength(1);
  });

  it("uses browser fragment repairs for malformed tables and misnested prose", () => {
    const pages = htmlPages('<h1>First</h1><table>Before<tr><td>Cell</table><p>Body<div>Nested</div></p><h2>Second</h2><p>End');
    expect(pages).toHaveLength(2);
    const first = document.createElement("div");
    first.innerHTML = pages[0].text;
    expect(first.querySelector("tbody td")?.textContent).toBe("Cell");
    expect(first.textContent).toContain("Before");
    expect(first.querySelector("div")?.textContent).toBe("Nested");
    expect(pages[1].text).toContain("End");
  });

  it.each([
    '<h1>Safe</h1><script>alert(1)</script>',
    '<h1>Safe</h1><img src="https://tracker.example/pixel">',
    '<h1>Safe</h1><img srcset="/track 1x">',
    '<h1 onmouseover="alert(1)">Unsafe</h1>',
    '<a href="jav&#x09;ascript:alert(1)">Unsafe</a>',
    '<a href="data:text/html,unsafe">Unsafe</a>',
    '<a href="file:///etc/passwd">Unsafe</a>',
    '<div style="background:url(https://tracker.example)">Unsafe</div>',
    '<iframe src="https://tracker.example"></iframe>',
    '<svg><a href="javascript:alert(1)">Unsafe</a></svg>',
    '<form action="/delete"><button>Unsafe</button></form>',
    '<noscript><h1>Invisible parser-dependent content</h1></noscript>',
    '<template><h1>Hidden content</h1></template>',
  ])("refuses active or network-loading markup without manufacturing a sanitized replacement: %s", (html) => {
    expect(paginateHtml(html)).toEqual({ kind: "unsafe", pages: [] });
  });

  it("accepts existing safe server attributes and voluntary HTTP links", () => {
    const pages = htmlPages('<h1 id="safe" lang="en" dir="auto" title="Heading">Safe</h1><p><a href="https://example.org" target="_blank" rel="noopener">Source</a><a href="../relative">Relative</a></p><ol start="2"><li>One</li></ol><table><tr><th colspan="2" scope="row">Two</th></tr></table>');
    expect(pages).toHaveLength(1);
    expect(pages[0].fragmentIds).toEqual(["safe"]);
  });

  it("does not withhold a safe body merely because its voluntary HTTP link is incomplete", () => {
    const source = '<h1>Readable</h1><p><a href="https://">Incomplete source link</a></p>';
    const pages = htmlPages(source);
    expect(pages).toHaveLength(1);
    expect(pages[0].text).toContain('href="https://"');
  });

  it("does not advertise duplicate fragment IDs as destinations", () => {
    const pages = htmlPages('<h1 id="same">First</h1><p id="same">Ambiguous</p><h2 id="second">Second</h2><p id="same">Also ambiguous</p>');
    expect(pages[0].fragmentIds).toEqual([]);
    expect(pages[1].fragmentIds).toEqual(["second"]);
  });
});

describe("TOC destination admission", () => {
  const toc = [
    { title: "Opening", page_index: 0, level: 0 },
    { title: "Evidence", page_index: 1, level: 1 },
    { title: "Missing", page_index: 8, level: 0 },
    { title: "Stale title", page_index: 1, level: 0 },
    { title: "Unknown", page_index: null, level: 0 },
  ];
  it("allows only matching HTML headings at an actual server ordinal", () => {
    const pages = htmlPages('<h1>Opening</h1><h2> Evidence\n </h2>');
    expect(readerToc(toc, pages, true, true).map((entry) => entry.page_index)).toEqual([0, 1, null, null, null]);
    expect(readerToc(toc, pages, true, false).every((entry) => entry.page_index === null)).toBe(true);
  });
  it("lists every unreadable reference without offering page jumps", () => {
    const result = readerToc(toc, htmlPages('<h1>Opening</h1>'), false, true);
    expect(result.map((entry) => entry.title)).toEqual(toc.map((entry) => entry.title));
    expect(result.every((entry) => entry.page_index === null)).toBe(true);
  });
  it("preserves Markdown/PDF page references without requiring heading equality", () => {
    expect(readerToc(toc, paginate('## Page 1\n\nFirst\n\n## Page 2\n\nSecond'), true, false).map((entry) => entry.page_index)).toEqual([0, 1, null, 1, null]);
  });
});
