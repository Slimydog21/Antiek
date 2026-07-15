import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useState } from "react";

import type {
  MultimediaAssetRecord,
  MultimediaKnowledgeFinalizationStatus,
  MultimediaKnowledgeLink,
} from "../../api/multimedia";
import {
  finalizeMultimediaKnowledge,
  getMultimediaKnowledgeFinalization,
  getMultimediaKnowledgeTwin,
  recoverMultimediaKnowledgeFinalization,
} from "../../api/multimedia";
import { KnowledgePanel, retainCurrentMultimediaSelection } from "./KnowledgePanel";

vi.mock("../../api/multimedia", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/multimedia")>();
  return {
    ...actual,
    finalizeMultimediaKnowledge: vi.fn(),
    getMultimediaKnowledgeFinalization: vi.fn(),
    getMultimediaKnowledgeTwin: vi.fn(),
    recoverMultimediaKnowledgeFinalization: vi.fn(),
  };
});

const getStatus = vi.mocked(getMultimediaKnowledgeFinalization);
const getTwin = vi.mocked(getMultimediaKnowledgeTwin);
const finalize = vi.mocked(finalizeMultimediaKnowledge);
const recover = vi.mocked(recoverMultimediaKnowledgeFinalization);

const LINK: MultimediaKnowledgeLink = {
  schema_version: "antiek.multimedia-knowledge-link.v1",
  asset_id: "asset-1",
  revision_id: "rev-1",
  source_document_id: "doc-1",
  source_event_id: "event-1",
  graph_node_id: "node-1",
  twin_document_id: "twin-1",
  source_html_sha256: "a".repeat(64),
  twin_html_sha256: "b".repeat(64),
  insight_node_ids: ["insight-1", "insight-2"],
  question_node_ids: ["question-1"],
};

function asset(revision = "rev-1", state = "ready"): MultimediaAssetRecord {
  return {
    asset: {
      asset_id: "asset-1",
      revision_id: revision,
      status: state,
      kind: "information_video",
      title: "Aircraft economics",
      route_policy: "balanced",
      requested_duration_minutes: 30,
      manifest: {},
    },
    plan: {},
    mode: "video",
    style: null,
    hardening_report: null,
    latest_steering_intent: null,
    jobs: [],
    knowledge_link: null,
    knowledge_finalization_revision_id: null,
  };
}

function status(
  state: MultimediaKnowledgeFinalizationStatus["distillation"]["state"],
  recoveryEligible = false,
  link: MultimediaKnowledgeLink | null = null,
  revision = "rev-1",
): MultimediaKnowledgeFinalizationStatus {
  return {
    asset_id: "asset-1",
    revision_id: revision,
    asset_status: "ready",
    distillation: {
      state,
      recovery_eligible: recoveryEligible,
      recovery_stale_seconds: 900,
      claim_started_at: state === "in_progress" ? "2026-07-12 01:00:00" : null,
    },
    knowledge_link: link,
  };
}

describe("KnowledgePanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(cleanup);

  it("does not inspect or finalize an unready asset", () => {
    render(<KnowledgePanel asset={asset("rev-1", "script_ready")} onAssetUpdated={vi.fn()} />);
    expect(screen.getByText(/complete this revision/i)).toBeTruthy();
    expect(getStatus).not.toHaveBeenCalled();
    expect(finalize).not.toHaveBeenCalled();
  });

  it("requires explicit model acknowledgement before initial finalization", async () => {
    getStatus.mockResolvedValue(status("not_started"));
    const linkedAsset = { ...asset(), knowledge_link: LINK };
    finalize.mockResolvedValue({ asset: linkedAsset, knowledge_link: LINK });
    const updated = vi.fn();
    const busy = vi.fn();
    render(<KnowledgePanel asset={asset()} onAssetUpdated={updated} onMutationBusyChange={busy} />);

    const button = await screen.findByRole("button", { name: "Create knowledge twin" });
    expect((button as HTMLButtonElement).disabled).toBe(true);
    expect(finalize).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("checkbox", { name: /approve one note-model call/i }));
    expect((button as HTMLButtonElement).disabled).toBe(false);
    fireEvent.click(button);

    await waitFor(() => expect(finalize).toHaveBeenCalledWith("asset-1", "rev-1"));
    expect(busy.mock.calls).toEqual([[true], [false]]);
    expect(updated).toHaveBeenCalledWith(linkedAsset);
    expect((await screen.findByTestId("multimedia-knowledge-evidence")).textContent).toContain("twin-1");
    expect(screen.getByTestId("multimedia-knowledge-evidence").textContent).toContain("2");
  });

  it("does not offer recovery for a fresh in-progress claim", async () => {
    getStatus.mockResolvedValue(status("in_progress"));
    render(<KnowledgePanel asset={asset()} onAssetUpdated={vi.fn()} />);
    expect(await screen.findByText(/reserved/i)).toBeTruthy();
    expect(screen.queryByRole("button", { name: /recover knowledge twin/i })).toBeNull();
    expect(recover).not.toHaveBeenCalled();
  });

  it("requires both acknowledgements before uncertain-outcome recovery", async () => {
    getStatus.mockResolvedValue(status("in_progress", true));
    recover.mockResolvedValue({ asset: { ...asset(), knowledge_link: LINK }, knowledge_link: LINK });
    render(<KnowledgePanel asset={asset()} onAssetUpdated={vi.fn()} />);

    const button = await screen.findByRole("button", { name: "Recover knowledge twin" });
    expect((button as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole("checkbox", { name: /approve another note-model call/i }));
    expect((button as HTMLButtonElement).disabled).toBe(true);
    expect(recover).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("checkbox", { name: /may duplicate model spend/i }));
    expect((button as HTMLButtonElement).disabled).toBe(false);
    fireEvent.click(button);
    await waitFor(() => expect(recover).toHaveBeenCalledWith("asset-1", "rev-1"));
  });

  it("shows completed evidence and clears consent when the revision changes", async () => {
    getStatus.mockResolvedValueOnce(status("in_progress", true));
    const { rerender } = render(<KnowledgePanel asset={asset()} onAssetUpdated={vi.fn()} />);
    fireEvent.click(await screen.findByRole("checkbox", { name: /approve another note-model call/i }));
    fireEvent.click(screen.getByRole("checkbox", { name: /may duplicate model spend/i }));

    getStatus.mockResolvedValueOnce(status("completed", false, { ...LINK, revision_id: "rev-2" }, "rev-2"));
    rerender(<KnowledgePanel asset={asset("rev-2")} onAssetUpdated={vi.fn()} />);

    expect((await screen.findByTestId("multimedia-knowledge-evidence")).textContent).toContain("twin-1");
    expect(screen.queryByRole("checkbox")).toBeNull();
    expect(recover).not.toHaveBeenCalled();
  });

  it("opens a cross-bound sandboxed twin and closes it", async () => {
    getStatus.mockResolvedValue(status("completed", false, LINK));
    getTwin.mockResolvedValue({
      asset_id: "asset-1",
      revision_id: "rev-1",
      source_document_id: "doc-1",
      twin_document_id: "twin-1",
      title: "Twin notes: Aircraft economics",
      html: "<!doctype html><html><body><h1>Twin</h1></body></html>",
      html_sha256: "b".repeat(64),
    });
    render(<KnowledgePanel asset={asset()} onAssetUpdated={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "Open twin" }));
    const frame = await screen.findByTitle("Twin notes: Aircraft economics");
    expect(frame.getAttribute("sandbox")).toBe("");
    expect(frame.getAttribute("srcdoc")).toContain("<h1>Twin</h1>");
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(screen.queryByTestId("multimedia-twin-viewer")).toBeNull();
  });

  it("rejects a twin response detached from the displayed link", async () => {
    getStatus.mockResolvedValue(status("completed", false, LINK));
    getTwin.mockResolvedValue({
      asset_id: "asset-1",
      revision_id: "rev-1",
      source_document_id: "doc-other",
      twin_document_id: "twin-1",
      title: "Detached",
      html: "<!doctype html><html><body>Detached</body></html>",
      html_sha256: "b".repeat(64),
    });
    render(<KnowledgePanel asset={asset()} onAssetUpdated={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "Open twin" }));
    expect((await screen.findByRole("alert")).textContent).toMatch(/integrity check/i);
    expect(screen.queryByTestId("multimedia-twin-viewer")).toBeNull();
  });

  it("does not reopen a stale twin after the asset identity changes", async () => {
    getStatus
      .mockResolvedValueOnce(status("completed", false, LINK))
      .mockResolvedValueOnce({
        ...status("not_started", false, null, "rev-2"),
        asset_id: "asset-2",
      });
    let finish: ((document: Awaited<ReturnType<typeof getMultimediaKnowledgeTwin>>) => void) | undefined;
    getTwin.mockReturnValue(new Promise((resolve) => { finish = resolve; }));
    const { rerender } = render(<KnowledgePanel asset={asset()} onAssetUpdated={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "Open twin" }));

    const next = {
      ...asset("rev-2"),
      asset: { ...asset("rev-2").asset, asset_id: "asset-2" },
    };
    rerender(<KnowledgePanel asset={next} onAssetUpdated={vi.fn()} />);
    finish?.({
      asset_id: "asset-1",
      revision_id: "rev-1",
      source_document_id: "doc-1",
      twin_document_id: "twin-1",
      title: "Stale twin",
      html: "<!doctype html><html><body>Stale</body></html>",
      html_sha256: "b".repeat(64),
    });
    await waitFor(() => expect(getStatus).toHaveBeenCalledTimes(2));
    expect(screen.queryByTestId("multimedia-twin-viewer")).toBeNull();
  });

  it("does not apply stale finalization status after the asset changes", async () => {
    let finishFirst: ((value: MultimediaKnowledgeFinalizationStatus) => void) | undefined;
    getStatus
      .mockReturnValueOnce(new Promise((resolve) => { finishFirst = resolve; }))
      .mockResolvedValueOnce({
        ...status("not_started", false, null, "rev-2"),
        asset_id: "asset-2",
      });
    const { rerender } = render(<KnowledgePanel asset={asset()} onAssetUpdated={vi.fn()} />);
    const next = {
      ...asset("rev-2"),
      asset: { ...asset("rev-2").asset, asset_id: "asset-2" },
    };
    rerender(<KnowledgePanel asset={next} onAssetUpdated={vi.fn()} />);
    await screen.findByRole("button", { name: "Create knowledge twin" });
    finishFirst?.(status("completed", false, LINK));
    await waitFor(() => expect(getStatus).toHaveBeenCalledTimes(2));
    expect(screen.queryByRole("button", { name: "Open twin" })).toBeNull();
    expect(screen.getByRole("button", { name: "Create knowledge twin" })).toBeTruthy();
  });

  it("rejects a status response for another revision", async () => {
    getStatus.mockResolvedValue(status("not_started", false, null, "rev-other"));
    render(<KnowledgePanel asset={asset()} onAssetUpdated={vi.fn()} />);
    expect((await screen.findByRole("alert")).textContent).toMatch(/revision changed/i);
    expect(finalize).not.toHaveBeenCalled();
  });

  it("rejects status evidence bound to another asset", async () => {
    getStatus.mockResolvedValue({
      ...status("completed", false, { ...LINK, asset_id: "asset-other" }),
      asset_id: "asset-1",
    });
    render(<KnowledgePanel asset={asset()} onAssetUpdated={vi.fn()} />);
    expect((await screen.findByRole("alert")).textContent).toMatch(/revision changed/i);
    expect(screen.queryByTestId("multimedia-knowledge-evidence")).toBeNull();
  });

  it("does not replace a newer selection with a late finalization result", () => {
    const current = { ...asset("rev-2"), asset: { ...asset("rev-2").asset, asset_id: "asset-2" } };
    const staleResult = { ...asset(), knowledge_link: LINK };
    expect(retainCurrentMultimediaSelection(current, "asset-1", "rev-1", staleResult)).toBe(current);
    expect(retainCurrentMultimediaSelection(asset(), "asset-1", "rev-1", staleResult)).toBe(staleResult);
  });

  it("holds the parent selection lock for the full model mutation", async () => {
    getStatus.mockResolvedValue(status("not_started"));
    let finish: ((value: Awaited<ReturnType<typeof finalizeMultimediaKnowledge>>) => void) | undefined;
    finalize.mockReturnValue(new Promise((resolve) => { finish = resolve; }));

    function Harness() {
      const [busy, setBusy] = useState(false);
      return (
        <>
          <button type="button" disabled={busy}>Open another asset</button>
          <KnowledgePanel asset={asset()} onAssetUpdated={vi.fn()} onMutationBusyChange={setBusy} />
        </>
      );
    }

    render(<Harness />);
    fireEvent.click(await screen.findByRole("checkbox", { name: /approve one note-model call/i }));
    fireEvent.click(screen.getByRole("button", { name: "Create knowledge twin" }));
    expect((screen.getByRole("button", { name: "Open another asset" }) as HTMLButtonElement).disabled).toBe(true);
    finish?.({ asset: { ...asset(), knowledge_link: LINK }, knowledge_link: LINK });
    await waitFor(() => {
      expect((screen.getByRole("button", { name: "Open another asset" }) as HTMLButtonElement).disabled).toBe(false);
    });
  });

  it("rejects a mismatched finalization response before updating the selection", async () => {
    getStatus.mockResolvedValue(status("not_started"));
    finalize.mockResolvedValue({
      asset: asset("rev-other"),
      knowledge_link: { ...LINK, revision_id: "rev-other" },
    });
    const updated = vi.fn();
    render(<KnowledgePanel asset={asset()} onAssetUpdated={updated} />);
    fireEvent.click(await screen.findByRole("checkbox", { name: /approve one note-model call/i }));
    fireEvent.click(screen.getByRole("button", { name: "Create knowledge twin" }));
    const alert = await screen.findByRole("alert");
    await waitFor(() => expect(updated).not.toHaveBeenCalled());
    expect(alert.textContent).toMatch(/state changed/i);
  });
});
