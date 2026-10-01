import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { DeliverableDetailResponse } from "../../lib/api";
import { createInMemoryTabTreeAdapter } from "../../workspace/tabTree";
import { getTabOwner, setTabOwner } from "../../workspace/tabTreeOwner";
import { useTabTrees } from "../../workspace/tabTreeStore";
import { sectionRefOf } from "../../workspace/writeTreeSync";

// Descendant editors/repository are outside this read and tab-seeding
// lifetime. WriteHome, getDeliverable, useWriteTreeSync and the store are real.
vi.mock("./Outline", () => ({ default: ({ sections, onChanged }: {
  sections: DeliverableDetailResponse["sections"];
  onChanged: () => void;
}) => <><button onClick={onChanged}>Reload detail</button>{sections.map((section) => <p key={section.section_id}>{section.title}</p>)}</> }));
vi.mock("./BlockRepository", () => ({ default: () => null }));
import WriteHome from "./WriteHome";

const tabs = () => useTabTrees.getState();
const drain = async () => { await act(async () => { for (let i = 0; i < 160; i++) await Promise.resolve(); }); };
function deferredResponse() {
  let resolve: (response: Response) => void = () => { throw new Error("not initialized"); };
  const promise = new Promise<Response>((done) => { resolve = done; });
  return { promise, resolve };
}
function detail(title: string, sectionId: string): DeliverableDetailResponse {
  return {
    deliverable_id: "piece", title, deliverable_kind: "general_essay", status: "draft", investigation_root_id: null,
    sections: [{ section_id: sectionId, deliverable_id: "piece", parent_section_id: null, section_index: 0, title: sectionId, prose_text: null, prose_provenance: null, block_count: 0 }],
  };
}
const json = (body: unknown) => new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
const refs = () => Object.values(tabs().trees.writing?.nodes ?? {}).map((node) => node.ref);

beforeEach(() => {
  setTabOwner(null); setTabOwner("owner-A"); tabs().resetTabTrees();
  vi.stubGlobal("matchMedia", () => ({ matches: false, addEventListener: () => {}, removeEventListener: () => {} }));
});
afterEach(() => { cleanup(); setTabOwner(null); tabs().resetTabTrees(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

it.each(["owner", "project"] as const)("refreshes authorized detail on a mounted %s change and rejects an old detail completion", async (boundary) => {
  const obsolete = deferredResponse();
  const authorized = deferredResponse();
  const requests: string[] = [];
  vi.stubGlobal("fetch", vi.fn<typeof fetch>(async (input) => {
    if (!String(input).endsWith("/deliverables/piece")) throw new Error(`unexpected request ${String(input)}`);
    requests.push(`${getTabOwner().owner}/${tabs().projectId}`);
    if (requests.length === 1) return json(detail("Initial piece", "old-section"));
    return requests.length === 2 ? obsolete.promise : authorized.promise;
  }));
  await tabs().bindActiveProject(async () => "project-A", () => createInMemoryTabTreeAdapter());
  await tabs().ensureMothership("writing");
  render(<MemoryRouter initialEntries={["/write/piece"]}><Routes><Route path="/write/:deliverableId" element={<WriteHome />} /></Routes></MemoryRouter>);
  await screen.findByText("Initial piece");
  await drain();
  expect(refs()).toContain(sectionRefOf("old-section"));
  fireEvent.click(screen.getByRole("button", { name: "Reload detail" }));
  await drain();
  expect(requests).toHaveLength(2);
  await act(async () => {
    if (boundary === "owner") setTabOwner("owner-B");
    await tabs().bindActiveProject(async () => "project-B", () => createInMemoryTabTreeAdapter());
    await tabs().ensureMothership("writing");
  });
  await drain();
  expect(requests).toEqual(["owner-A/project-A", "owner-A/project-A", `${boundary === "owner" ? "owner-B" : "owner-A"}/project-B`]);
  expect(screen.queryByText("Initial piece")).toBeNull();
  await act(async () => { obsolete.resolve(json(detail("Obsolete piece", "obsolete-section"))); });
  await drain();
  expect(screen.queryByText("Obsolete piece")).toBeNull();
  expect(refs()).not.toContain(sectionRefOf("obsolete-section"));
  expect(refs()).not.toContain(sectionRefOf("old-section"));
  await act(async () => { authorized.resolve(json(detail("Authorized piece", "new-section"))); });
  await drain();
  expect(screen.getByText("Authorized piece")).toBeTruthy();
  expect(refs()).toContain(sectionRefOf("new-section"));
  expect(refs()).not.toContain(sectionRefOf("old-section"));
  expect(refs()).not.toContain(sectionRefOf("obsolete-section"));
});
