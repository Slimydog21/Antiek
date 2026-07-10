import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import HtmlReader, { validateBornAntiekHtml } from "./HtmlReader";

const html = `<article id="antiek-anchor-one" data-source-page="3"><p>alpha repeated repeated omega</p></article>`;

afterEach(() => cleanup());

describe("HtmlReader", () => {
  it.each([
    `<script>alert(1)</script>`, `<img src="https://evil.invalid/x">`, `<p onclick="evil()">x</p>`,
    `<iframe srcdoc="x"></iframe>`, `<svg><text>x</text></svg>`, `<p style="background:url(x)">x</p>`,
    `<article><style>*{display:none}</style></article>`, `<a ping="https://evil.invalid">x</a>`,
    `<article><title onclick="evil()">x</title></article>`,
  ])("rejects active or foreign markup", (value) => expect(() => validateBornAntiekHtml(value)).toThrow(/Rejected/));

  it("shows a closed failure surface for rejected HTML", () => {
    const { container } = render(<HtmlReader html="<script>alert(1)</script>" investigationId="i" documentId="d" onRegionSelected={vi.fn()} />);
    expect(screen.getByRole("alert").textContent).toMatch(/safety check failed/);
    expect(container.querySelector("script")).toBeNull();
  });

  it("renders direct HTML, preserves anchors, focuses, and adjusts text size", () => {
    const { container } = render(<HtmlReader html={html} investigationId="i" documentId="d" onRegionSelected={vi.fn()} />);
    expect(container.querySelector("iframe,object,embed,canvas")).toBeNull();
    expect(container.querySelector("#antiek-anchor-one")).not.toBeNull();
    const content = screen.getByLabelText("Document content"); content.focus(); expect(document.activeElement).toBe(content);
    fireEvent.click(screen.getByLabelText("Increase text size")); expect(screen.getByLabelText("Text size").textContent).toBe("113%");
    fireEvent.click(screen.getByLabelText("Decrease text size")); expect(screen.getByLabelText("Text size").textContent).toBe("100%");
  });

  it("emits typed payload with exact repeated-text offsets and lineage", () => {
    const callback = vi.fn();
    render(<HtmlReader html={html} investigationId="investigation-1" documentId="document-1" onRegionSelected={callback} />);
    const node = document.querySelector("#antiek-anchor-one p")!.firstChild!;
    const range = document.createRange(); range.setStart(node, 15); range.setEnd(node, 23);
    const selection = window.getSelection()!; selection.removeAllRanges(); selection.addRange(range);
    fireEvent.mouseUp(screen.getByLabelText("Document content"));
    expect(callback).toHaveBeenCalledWith(expect.objectContaining({
      investigationId: "investigation-1", documentId: "document-1",
      payload: expect.objectContaining({ action_type: "document.region_selected", page: 3, char_start: 15, char_end: 23, text_excerpt: "repeated" }),
      anchor: expect.objectContaining({ anchorId: "antiek-anchor-one", exact: "repeated" }),
    }));
  });

  it("deep-links and exposes restore resolution", () => {
    const scroll = vi.fn(); Element.prototype.scrollIntoView = scroll;
    const restored = vi.fn();
    const region = { anchorId: "antiek-anchor-one", charStart: 6, charEnd: 14, exact: "repeated", prefix: "alpha ", suffix: " repeated omega", sourcePage: 3 };
    render(<HtmlReader html={html} investigationId="i" documentId="d" restoreRegion={region} onRestoreResult={restored} onRegionSelected={vi.fn()} />);
    expect(restored).toHaveBeenCalledWith(expect.objectContaining({ status: "resolved" }));
    expect(scroll).toHaveBeenCalled();
  });
});
