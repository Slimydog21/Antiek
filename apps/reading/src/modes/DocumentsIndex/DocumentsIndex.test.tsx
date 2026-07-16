import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import DocumentsIndex from "./index";

const apiFetchMock = vi.fn();
const navigateMock = vi.fn();

vi.mock("../../lib/api", () => ({ apiFetch: (...args: unknown[]) => apiFetchMock(...args) }));
vi.mock("react-router-dom", () => ({ useNavigate: () => navigateMock }));
vi.mock("../../components/lemon/LemonTag", () => ({ default: ({ children }: { children: React.ReactNode }) => <span>{children}</span> }));
vi.mock("../../components/lemon/LemonTable", () => ({
  default: ({ rows, rowKey, onRowClick }: { rows: Array<{ document_id: string; title: string }>; rowKey: (row: { document_id: string }) => string; onRowClick: (row: { document_id: string }) => void }) => (
    <div>{rows.map((row) => <button key={rowKey(row)} onClick={() => onRowClick(row)}>{row.title}</button>)}</div>
  ),
}));

const ok = (documents: unknown[] = []) => Promise.resolve({ ok: true, json: async () => ({ documents }) });

describe("DocumentsIndex — evidence archive atlas", () => {
  beforeEach(() => { apiFetchMock.mockReset(); navigateMock.mockReset(); apiFetchMock.mockImplementation(() => ok()); });
  afterEach(cleanup);

  it("keeps generated art decorative and renders one live archive heading", async () => {
    render(<DocumentsIndex />);
    expect(screen.getByTestId("evidence-archive-atlas-art").getAttribute("aria-hidden")).toBe("true");
    expect(screen.getByRole("heading", { name: "Survey what the substrate holds" })).toBeTruthy();
    await waitFor(() => expect(apiFetchMock).toHaveBeenCalledWith("/documents?limit=500"));
  });

  it("preserves tier and trimmed investigation query construction", async () => {
    render(<DocumentsIndex />);
    await waitFor(() => expect(apiFetchMock).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByRole("button", { name: "tier 3" }));
    await waitFor(() => expect(apiFetchMock).toHaveBeenCalledWith("/documents?source_tier=3&limit=500"));
    fireEvent.change(screen.getByLabelText("Investigation id"), { target: { value: "  inv-polar  " } });
    await waitFor(() => expect(apiFetchMock).toHaveBeenCalledWith("/documents?source_tier=3&investigation_id=inv-polar&limit=500"));
  });

  it("opens the encoded authoritative reader route", async () => {
    apiFetchMock.mockImplementation(() => ok([{ document_id: "doc/ice map", title: "Ice map", source_uri: null, document_type: "html", source_tier: 1, investigation_id: null, content_class: null, ip_holder_id: null }]));
    render(<DocumentsIndex />);
    fireEvent.click(await screen.findByRole("button", { name: "Ice map" }));
    expect(navigateMock).toHaveBeenCalledWith("/wrestle/doc%2Fice%20map");
  });

  it("never renders raw fetch or HTTP details", async () => {
    apiFetchMock.mockRejectedValue(new Error("Authorization Bearer archive-secret /private/path"));
    render(<DocumentsIndex />);
    expect(await screen.findByText("The archive could not be charted. Try again.")).toBeTruthy();
    expect(screen.queryByText(/archive-secret|private\/path|GET \/documents/i)).toBeNull();
  });
});
