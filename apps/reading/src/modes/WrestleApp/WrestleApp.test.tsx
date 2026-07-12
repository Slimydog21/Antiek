import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";

const { ingestHostedDocument, fetchHostedDocument, postTypedEvent, routeParams } = vi.hoisted(
  () => ({
    ingestHostedDocument: vi.fn(),
    fetchHostedDocument: vi.fn(),
    postTypedEvent: vi.fn(),
    routeParams: {} as { documentId?: string },
  }),
);

vi.mock("react-router-dom", () => ({ useParams: () => routeParams }));
vi.mock("../../api/hostedDocuments", () => ({
  ingestHostedDocument,
  fetchHostedDocument,
}));
vi.mock("../../hooks/useEventStream", () => ({
  useEventStream: () => ({ events: [], status: "open", reconnects: 0 }),
}));
vi.mock("../../lib/api", () => ({ postTypedEvent }));
vi.mock("../../components/windows/HostedHtmlDocumentHost", () => ({
  default: (props: {
    document_id: string;
    html: string;
    onHighlightSelection?: (selection: {
      text: string;
      charStart: number;
      charEnd: number;
    }) => void;
  }) => (
    <article
      data-testid="shared-hosted-html-document"
      data-document-id={props.document_id}
      data-html={props.html}
      onMouseUp={() =>
        props.onHighlightSelection?.({
          text: "selected canonical passage",
          charStart: 0,
          charEnd: 26,
        })
      }
    >
      selected canonical passage
    </article>
  ),
}));
vi.mock("../../workspace/PanelHost", () => ({
  PanelHost: ({
    children,
    starters,
  }: {
    children: ReactNode;
    starters: unknown[];
  }) => <main data-starter-count={starters.length}>{children}</main>,
}));

import WrestleApp from ".";

afterEach(cleanup);

const readyReceipt = {
  document_id: "hdoc_server_owned",
  owner_id: "owner",
  state: "ready",
  source_byte_hash: "sha256:source",
  canonical_content_hash: "sha256:canonical",
  source_format: "html",
  title: "Research file",
  document_loaded_event_id: "evt-server",
  already_hosted: false,
  non_viewable_reason: null,
  view_format: "html",
  html: "<!doctype html><html><body><p>selected canonical passage</p></body></html>",
};

describe("WrestleApp canonical hosted transport", () => {
  beforeEach(() => {
    sessionStorage.clear();
    delete routeParams.documentId;
    ingestHostedDocument.mockReset().mockResolvedValue(readyReceipt);
    fetchHostedDocument.mockReset();
    postTypedEvent.mockReset().mockResolvedValue({ event_id: "evt-region" });
  });

  it("uploads to server ingest and renders canonical HTML without client document.loaded", async () => {
    render(<WrestleApp />);
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(
      ["<html><body>" + "research ".repeat(60) + "</body></html>"],
      "research.html",
      { type: "text/html" },
    );
    fireEvent.change(input, { target: { files: [file] } });

    expect(
      (await screen.findByTestId("shared-hosted-html-document")).getAttribute(
        "data-document-id",
      ),
    ).toBe("hdoc_server_owned");
    expect(ingestHostedDocument).toHaveBeenCalledWith(
      expect.objectContaining({
        source_format: "html",
        title: "research.html",
      }),
    );
    expect(postTypedEvent).not.toHaveBeenCalled();
    expect(document.body.textContent).not.toContain("Load a PDF to wrestle");
    expect(document.querySelector("main")?.getAttribute("data-starter-count")).toBe("2");
  });

  it("emits only document.region_selected for a canonical HTML selection", async () => {
    render(<WrestleApp />);
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, {
      target: {
        files: [new File(["x"], "research.txt", { type: "text/plain" })],
      },
    });
    const article = await screen.findByTestId("shared-hosted-html-document");
    fireEvent.mouseUp(article);

    await waitFor(() => expect(postTypedEvent).toHaveBeenCalledTimes(1));
    const envelope = postTypedEvent.mock.calls[0][0];
    expect(envelope.document_id).toBe("hdoc_server_owned");
    expect(envelope.payload.action_type).toBe("document.region_selected");
    expect(envelope.payload.text_excerpt).toBe("selected canonical passage");
  });

  it("does not activate panels for an unauthorized route document id", async () => {
    routeParams.documentId = "hdoc_other_owner";
    fetchHostedDocument.mockRejectedValue(
      new Error("hosted document API 403: other account"),
    );
    render(<WrestleApp />);

    expect(await screen.findByText(/hosted document API 403/)).toBeTruthy();
    expect(document.querySelector("main")?.getAttribute("data-starter-count")).toBe("0");
    expect(screen.queryByTestId("shared-hosted-html-document")).toBeNull();
  });

  it("passes server HTML and identity into the shared sanitized interaction host", async () => {
    ingestHostedDocument.mockResolvedValue({
      ...readyReceipt,
      html: '<p>safe</p><img src="x" onerror="steal()"><script>attack()</script>',
    });
    render(<WrestleApp />);
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, {
      target: { files: [new File(["safe"], "safe.html", { type: "text/html" })] },
    });
    const article = await screen.findByTestId("shared-hosted-html-document");
    expect(article.getAttribute("data-document-id")).toBe("hdoc_server_owned");
    expect(article.getAttribute("data-html")).toContain("<script>attack()</script>");
  });

  it("clears an authorized document before a changed route id is accepted", async () => {
    routeParams.documentId = "hdoc_allowed";
    fetchHostedDocument.mockResolvedValueOnce(readyReceipt);
    const view = render(<WrestleApp />);
    expect(await screen.findByTestId("shared-hosted-html-document")).toBeTruthy();

    routeParams.documentId = "hdoc_denied";
    fetchHostedDocument.mockRejectedValueOnce(new Error("hosted document API 403"));
    view.rerender(<WrestleApp />);

    expect(await screen.findByText(/hosted document API 403/)).toBeTruthy();
    expect(screen.queryByTestId("shared-hosted-html-document")).toBeNull();
    expect(document.querySelector("main")?.getAttribute("data-starter-count")).toBe("0");
  });

  it("surfaces a failed region event without discarding the hosted document", async () => {
    postTypedEvent.mockRejectedValueOnce(new Error("event log unavailable"));
    render(<WrestleApp />);
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, {
      target: { files: [new File(["x"], "research.txt", { type: "text/plain" })] },
    });
    const host = await screen.findByTestId("shared-hosted-html-document");
    fireEvent.mouseUp(host);

    expect((await screen.findByRole("alert")).textContent).toContain(
      "Highlight event failed: event log unavailable",
    );
    expect(screen.getByTestId("shared-hosted-html-document")).toBeTruthy();
  });
});
