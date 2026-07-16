import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import NotebooksIndex from "./index";

const apiFetchMock = vi.fn();
const navigateMock = vi.fn();

vi.mock("../../lib/api", () => ({ apiFetch: (...args: unknown[]) => apiFetchMock(...args) }));
vi.mock("react-router-dom", () => ({ useNavigate: () => navigateMock }));
vi.mock("../../components/lemon/LemonTag", () => ({ default: ({ children }: { children: React.ReactNode }) => <span>{children}</span> }));
vi.mock("../../components/lemon/LemonTable", () => ({
  default: ({ rows, rowKey, onRowClick }: { rows: Array<{ notebook_id: string; title: string }>; rowKey: (row: { notebook_id: string }) => string; onRowClick: (row: { notebook_id: string }) => void }) => (
    <div>{rows.map((row) => <button key={rowKey(row)} onClick={() => onRowClick(row)}>{row.title}</button>)}</div>
  ),
}));

const notebook = (overrides: Record<string, unknown> = {}) => ({
  notebook_id: "nb-1",
  title: "Research field notes",
  investigation_id: null,
  document_id: null,
  content_class: "user_owned",
  created_at: "2026-07-01",
  updated_at: "2026-07-15",
  ...overrides,
});
const listOk = (notebooks: unknown[] = []) => Promise.resolve({ ok: true, json: async () => ({ count: notebooks.length, notebooks }) });

describe("NotebooksIndex — recursive notebook conservatory", () => {
  beforeEach(() => { apiFetchMock.mockReset(); navigateMock.mockReset(); apiFetchMock.mockImplementation(() => listOk()); });
  afterEach(cleanup);

  it("keeps generated art decorative and surveys the exact notebook endpoint", async () => {
    render(<NotebooksIndex />);
    expect(screen.getByTestId("recursive-notebook-conservatory-art").getAttribute("aria-hidden")).toBe("true");
    expect(screen.getByRole("heading", { name: "Cultivate the notes that think with you" })).toBeTruthy();
    await waitFor(() => expect(apiFetchMock).toHaveBeenCalledWith("/notebooks"));
  });

  it("posts the trimmed authoritative create payload and opens the encoded notebook", async () => {
    apiFetchMock.mockImplementationOnce(() => listOk()).mockImplementationOnce(() => Promise.resolve({ ok: true, json: async () => notebook({ notebook_id: "nb/ice map" }) }));
    render(<NotebooksIndex />);
    await waitFor(() => expect(apiFetchMock).toHaveBeenCalledTimes(1));
    fireEvent.change(screen.getByLabelText("Notebook title"), { target: { value: "  Polar claims  " } });
    fireEvent.change(screen.getByLabelText(/Investigation ID/), { target: { value: "  inv-polar  " } });
    fireEvent.click(screen.getByRole("button", { name: "Create notebook" }));
    await waitFor(() => expect(apiFetchMock).toHaveBeenLastCalledWith("/notebooks", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: "Polar claims", investigation_id: "inv-polar" }),
    }));
    await waitFor(() => expect(navigateMock).toHaveBeenCalledWith("/notebook/nb%2Fice%20map"));
  });

  it("filters by the exact content class without refetching", async () => {
    apiFetchMock.mockImplementation(() => listOk([notebook(), notebook({ notebook_id: "nb-2", title: "Public notebook", content_class: "user_public_contribution" })]));
    render(<NotebooksIndex />);
    expect(await screen.findByRole("button", { name: "Public notebook" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "user owned" }));
    expect(screen.queryByRole("button", { name: "Public notebook" })).toBeNull();
    expect(apiFetchMock).toHaveBeenCalledTimes(1);
  });

  it("opens an existing notebook through the encoded authoritative route", async () => {
    apiFetchMock.mockImplementation(() => listOk([notebook({ notebook_id: "nb/field book" })]));
    render(<NotebooksIndex />);
    fireEvent.click(await screen.findByRole("button", { name: "Research field notes" }));
    expect(navigateMock).toHaveBeenCalledWith("/notebook/nb%2Ffield%20book");
  });

  it("keeps list and create boundary details private", async () => {
    apiFetchMock.mockRejectedValueOnce(new Error("Authorization Bearer notebook-secret /private/list"));
    render(<NotebooksIndex />);
    expect(await screen.findByText("The notebook conservatory could not be surveyed. Try again.")).toBeTruthy();
    expect(screen.queryByText(/notebook-secret|private\/list|GET \/notebooks/i)).toBeNull();
  });

  it("keeps create failure details private", async () => {
    apiFetchMock
      .mockImplementationOnce(() => listOk())
      .mockRejectedValueOnce(new Error("Authorization Bearer create-secret /private/create"));
    render(<NotebooksIndex />);
    await waitFor(() => expect(apiFetchMock).toHaveBeenCalledTimes(1));
    fireEvent.change(screen.getByLabelText("Notebook title"), { target: { value: "Polar claims" } });
    fireEvent.click(screen.getByRole("button", { name: "Create notebook" }));
    expect(await screen.findByText("The notebook could not be planted. Try again.")).toBeTruthy();
    expect(screen.queryByText(/create-secret|private\/create|POST \/notebooks/i)).toBeNull();
  });
});
