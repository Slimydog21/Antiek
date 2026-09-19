import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ArtifactOutlineShelf from "./ArtifactOutlineShelf";
import { getResearchArtifactBlocks, getResearchArtifactClaims } from "../../lib/api";

vi.mock("../../lib/api", () => ({
  exportResearchArtifact: vi.fn(),
  getResearchArtifactBlocks: vi.fn(),
  getResearchArtifactClaims: vi.fn(),
}));
vi.mock("../../lib/auth", () => ({ useAuth: () => ({ sessionGeneration: 4 }) }));
vi.mock("../../components/windows/openWindow", () => ({ openWindow: vi.fn() }));
vi.mock("../../workspace/actions", () => ({ openClaimInspector: vi.fn() }));

const blocks = vi.mocked(getResearchArtifactBlocks);
const claims = vi.mocked(getResearchArtifactClaims);

describe("ArtifactOutlineShelf claim projection", () => {
  beforeEach(() => {
    blocks.mockReset();
    claims.mockReset();
  });

  it("preserves outline blocks when the optional claim projection fails", async () => {
    blocks.mockResolvedValue({ investigation_id: "inv", blocks: [{
      node_id: "node-1", kind: "insight", label: "Durable outline block", investigation_id: "inv",
    }] });
    claims.mockRejectedValue(new Error("claims unavailable"));
    render(<ArtifactOutlineShelf investigationId="inv" />);
    expect(await screen.findByText("Durable outline block")).toBeTruthy();
  });

  it("does not commit a slower prior-investigation response", async () => {
    let resolveOld!: (value: Awaited<ReturnType<typeof getResearchArtifactBlocks>>) => void;
    blocks
      .mockReturnValueOnce(new Promise((resolve) => { resolveOld = resolve; }))
      .mockResolvedValueOnce({ investigation_id: "new", blocks: [{
        node_id: "new-node", kind: "insight", label: "New investigation block", investigation_id: "new",
      }] });
    claims
      .mockResolvedValueOnce({ investigation_id: "old", content_hash: "a".repeat(64), claims: [] })
      .mockResolvedValueOnce({ investigation_id: "new", content_hash: "b".repeat(64), claims: [] });
    const view = render(<ArtifactOutlineShelf investigationId="old" />);
    view.rerender(<ArtifactOutlineShelf investigationId="new" />);
    expect(await screen.findByText("New investigation block")).toBeTruthy();
    resolveOld({ investigation_id: "old", blocks: [{
      node_id: "old-node", kind: "insight", label: "Stale old block", investigation_id: "old",
    }] });
    await Promise.resolve();
    expect(screen.queryByText("Stale old block")).toBeNull();
  });
});
