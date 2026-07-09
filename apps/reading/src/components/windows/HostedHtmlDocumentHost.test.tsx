import { describe, expect, it, vi, afterEach } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

import HostedHtmlDocumentHost from "./HostedHtmlDocumentHost";

vi.mock("./windowHostContext", () => ({
  useInWindow: () => undefined,
}));

vi.mock("../engagement/TwinNotesPanel", () => ({
  TwinNotesPanel: (props: { assetId: string }) => (
    <div data-testid="twin-notes-panel-stub">{props.assetId}</div>
  ),
}));

vi.mock("../engagement/ResearchContextPanel", () => ({
  ResearchContextPanel: (props: { assetId: string }) => (
    <div data-testid="research-context-panel-stub">{props.assetId}</div>
  ),
}));

describe("HostedHtmlDocumentHost", () => {
  afterEach(() => cleanup());

  it("renders HTML body for hosted book", () => {
    render(
      <HostedHtmlDocumentHost
        document_id="doc_abc"
        title="Attention Is All You Need"
        view_format="html"
        license_class="public_domain"
        html="<article><h1>Attention</h1><p>Transformers.</p></article>"
      />,
    );
    expect(screen.getByTestId("hosted-html-document-host").getAttribute(
      "data-view-format",
    )).toBe("html");
    expect(screen.getByTestId("hosted-html-body").innerHTML).toMatch(
      /Attention/,
    );
    expect(screen.getByTestId("hosted-html-document-host").textContent).toMatch(
      /not PDF/,
    );
  });

  it("mounts twin notes + research context for document_id (bw)", () => {
    render(
      <HostedHtmlDocumentHost
        document_id="hdoc_xyz"
        title="Pride"
        view_format="html"
        html="<p>It is a truth</p>"
      />,
    );
    expect(screen.getByTestId("hosted-html-twins-mount")).toBeTruthy();
    expect(screen.getByTestId("twin-notes-panel-stub").textContent).toBe(
      "hdoc_xyz",
    );
    expect(screen.getByTestId("hosted-html-context-mount")).toBeTruthy();
    expect(screen.getByTestId("research-context-panel-stub").textContent).toBe(
      "hdoc_xyz",
    );
  });

  it("rejects non-html view_format", () => {
    render(
      <HostedHtmlDocumentHost
        document_id="doc_x"
        view_format="pdf"
        html="%PDF-1.4"
      />,
    );
    expect(screen.getByTestId("hosted-html-reject-pdf")).toBeTruthy();
  });
});
