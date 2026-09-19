import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const harness = vi.hoisted(() => ({
  generation: 1,
  authStatus: "authenticated",
  requests: [] as Array<{
    reference: { resolver: "hosted_document" | "engagement_document"; document_id: string };
    signal?: AbortSignal;
    resolve: (value: unknown) => void;
    reject: (reason: unknown) => void;
  }>,
}));

vi.mock("../../lib/auth", () => ({
  useAuth: () => ({
    state: harness.authStatus === "authenticated"
      ? { status: "authenticated", identity: { user_id: "alice" } }
      : { status: "anonymous" },
    sessionGeneration: harness.generation,
  }),
}));

vi.mock("../../api/htmlDocumentRefs", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/htmlDocumentRefs")>();
  return {
    ...actual,
    fetchHtmlDocumentReference: vi.fn(
      (reference: { resolver: "hosted_document" | "engagement_document"; document_id: string }, signal?: AbortSignal) =>
        new Promise((resolve, reject) => harness.requests.push({ reference, signal, resolve, reject })),
    ),
  };
});

vi.mock("./HostedHtmlDocumentHost", () => ({
  default: (props: Record<string, unknown>) => (
    <div data-testid="hosted-html-host" data-props={JSON.stringify(props)}>
      {String(props.title || "")}:{String(props.html || "")}
    </div>
  ),
}));

import HostedHtmlDocumentBridge from "./HostedHtmlDocumentBridge";

function hydrated(
  resolver: "hosted_document" | "engagement_document",
  documentId: string,
  title: string,
) {
  return {
    schema_version: 1 as const,
    resolver,
    document_id: documentId,
    title,
    view_format: "html" as const,
    html: `<!doctype html><html><body>${title} bytes</body></html>`,
  };
}

describe("HostedHtmlDocumentBridge authority and race fences", () => {
  beforeEach(() => {
    harness.generation = 1;
    harness.authStatus = "authenticated";
    harness.requests.length = 0;
  });
  afterEach(() => cleanup());

  it("keeps invalid references ephemeral but ignores every caller byte for an exact reference", async () => {
    const view = render(
      <HostedHtmlDocumentBridge
        document_id="same"
        title="caller title"
        view_format="html"
        html="<p>caller raw secret</p>"
        source="caller authority"
        resume_ref={{ resolver: "hosted_document", document_id: "same", extra: "invalid" }}
      />,
    );
    expect(screen.getByTestId("hosted-html-host").getAttribute("data-props")).toContain(
      "caller raw secret",
    );

    view.rerender(
      <HostedHtmlDocumentBridge
        document_id="caller-id"
        title="caller title"
        view_format="html"
        html="<p>caller raw secret</p>"
        source="caller authority"
        resume_ref={{ resolver: "hosted_document", document_id: "same" }}
      />,
    );
    expect(screen.getByTestId("hosted-html-reference-loading")).toBeTruthy();
    await act(async () => harness.requests[0].resolve(hydrated("hosted_document", "same", "Server title")));

    const props = JSON.parse(
      screen.getByTestId("hosted-html-host").getAttribute("data-props") || "{}",
    );
    expect(props).toEqual({
      document_id: "same",
      title: "Server title",
      view_format: "html",
      html: "<!doctype html><html><body>Server title bytes</body></html>",
    });
    expect(JSON.stringify(props)).not.toContain("caller");
  });

  it("aborts and discards a same-ID response from the prior resolver", async () => {
    const view = render(
      <HostedHtmlDocumentBridge resume_ref={{ resolver: "hosted_document", document_id: "same" }} />,
    );
    view.rerender(
      <HostedHtmlDocumentBridge resume_ref={{ resolver: "engagement_document", document_id: "same" }} />,
    );
    expect(harness.requests).toHaveLength(2);
    expect(harness.requests[0].signal?.aborted).toBe(true);

    await act(async () => harness.requests[0].resolve(hydrated("hosted_document", "same", "Stale host")));
    expect(screen.queryByText(/Stale host/)).toBeNull();
    await act(async () => harness.requests[1].resolve(hydrated("engagement_document", "same", "Current engagement")));
    expect(screen.getByText(/Current engagement/)).toBeTruthy();
  });

  it("hides already-rendered bytes immediately when the resolver changes", async () => {
    const view = render(
      <HostedHtmlDocumentBridge resume_ref={{ resolver: "hosted_document", document_id: "same" }} />,
    );
    await act(async () => harness.requests[0].resolve(hydrated("hosted_document", "same", "Old ready host")));
    expect(screen.getByText(/Old ready host/)).toBeTruthy();

    view.rerender(
      <HostedHtmlDocumentBridge resume_ref={{ resolver: "engagement_document", document_id: "same" }} />,
    );
    expect(screen.queryByText(/Old ready host/)).toBeNull();
    expect(screen.getByTestId("hosted-html-reference-loading")).toBeTruthy();
  });

  it("aborts and discards stale auth-generation results", async () => {
    const view = render(
      <HostedHtmlDocumentBridge resume_ref={{ resolver: "hosted_document", document_id: "same" }} />,
    );
    harness.generation = 2;
    view.rerender(
      <HostedHtmlDocumentBridge resume_ref={{ resolver: "hosted_document", document_id: "same" }} />,
    );
    expect(harness.requests[0].signal?.aborted).toBe(true);
    await act(async () => harness.requests[0].resolve(hydrated("hosted_document", "same", "Stale account")));
    expect(screen.queryByText(/Stale account/)).toBeNull();
    await act(async () => harness.requests[1].resolve(hydrated("hosted_document", "same", "Current account")));
    expect(screen.getByText(/Current account/)).toBeTruthy();
  });

  it("hides already-rendered bytes immediately on auth-generation change", async () => {
    const view = render(
      <HostedHtmlDocumentBridge resume_ref={{ resolver: "hosted_document", document_id: "same" }} />,
    );
    await act(async () => harness.requests[0].resolve(hydrated("hosted_document", "same", "Old account ready")));
    expect(screen.getByText(/Old account ready/)).toBeTruthy();

    harness.generation = 2;
    view.rerender(
      <HostedHtmlDocumentBridge resume_ref={{ resolver: "hosted_document", document_id: "same" }} />,
    );
    expect(screen.queryByText(/Old account ready/)).toBeNull();
    expect(screen.getByTestId("hosted-html-reference-loading")).toBeTruthy();
  });

  it("shows an unavailable state without raw fallback and retries explicitly", async () => {
    render(
      <HostedHtmlDocumentBridge
        title="caller secret"
        html="<p>caller secret</p>"
        resume_ref={{ resolver: "hosted_document", document_id: "same" }}
      />,
    );
    await act(async () => harness.requests[0].reject(new Error("denied")));
    expect(screen.getByTestId("hosted-html-reference-unavailable")).toBeTruthy();
    expect(screen.queryByText(/caller secret/)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(harness.requests).toHaveLength(2);
  });
});
