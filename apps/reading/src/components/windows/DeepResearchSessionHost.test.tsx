/**
 * DeepResearchSessionHost + WINDOW_PAGES eligibility for deep_research_session.
 * Residual (ag): mounts ResearchContextPanel with asset/spawn identity.
 * Residual (ah): mounts CollectiveResearchPanel with available spawn ids.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { DEEP_RESEARCH_WINDOW_KIND } from "../../workspace/deepResearchWindow";
import DeepResearchSessionHost from "./DeepResearchSessionHost";
import { WINDOW_PAGES, isWindowEligible, openWindow } from "./openWindow";
import { useWindows } from "../../workspace/windowsStore";

const FIXTURE = {
  session_id: "fsess_launch_1",
  spawn_id: "spn_launch_1",
  investigation_id: "inv_launch_1",
  parent_asset_id: "launch-asset",
  selection_text: "Transformer attention is content-addressable memory.",
  status: "reserved",
  view_format: "html" as const,
  model_id: "launch-model",
  region_id: "r-launch-1",
  goal: "Deep-research the highlighted passage",
};

describe("DeepResearchSessionHost", () => {
  afterEach(() => {
    cleanup();
  });

  it("renders session identity and selection from payload", () => {
    render(<DeepResearchSessionHost {...FIXTURE} />);
    expect(screen.getByTestId("deep-research-session-host")).toBeTruthy();
    expect(screen.getByText("fsess_launch_1")).toBeTruthy();
    // Spawn/parent appear in identity rows and ResearchContextPanel meta
    expect(screen.getAllByText("spn_launch_1").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("launch-asset").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("reserved")).toBeTruthy();
    expect(screen.getByTestId("deep-research-selection").textContent).toContain(
      "content-addressable",
    );
    expect(screen.getByText(/not PDF/i)).toBeTruthy();
    expect(
      screen.getByTestId("deep-research-session-host").getAttribute("data-view-format"),
    ).toBe("html");
  });

  it("mounts ResearchContextPanel with parent asset and spawn identity", () => {
    const first = render(<DeepResearchSessionHost {...FIXTURE} />);
    const mount = screen.getByTestId("deep-research-research-context-mount");
    expect(mount).toBeTruthy();
    expect(mount.getAttribute("data-view-format")).toBe("html");
    // Shipped panel chrome (not a reimplementation)
    expect(screen.getByRole("heading", { name: /research context/i })).toBeTruthy();
    expect(mount.textContent).toContain("launch-asset");
    expect(screen.getByTestId("load-research-context")).toBeTruthy();
    first.unmount();
    // Double-run: remount still binds panel
    render(<DeepResearchSessionHost {...FIXTURE} />);
    expect(screen.getByTestId("deep-research-research-context-mount")).toBeTruthy();
    expect(screen.getByTestId("load-research-context")).toBeTruthy();
  });

  it("omits ResearchContextPanel when parent_asset_id is missing", () => {
    const { parent_asset_id: _drop, ...noParent } = FIXTURE;
    render(<DeepResearchSessionHost {...noParent} />);
    expect(screen.queryByTestId("deep-research-research-context-mount")).toBeNull();
  });

  it("mounts CollectiveResearchPanel with available spawn ids from session", () => {
    useWindows.getState().reset();
    const first = render(<DeepResearchSessionHost {...FIXTURE} />);
    const mount = screen.getByTestId("deep-research-collective-mount");
    expect(mount).toBeTruthy();
    expect(mount.getAttribute("data-view-format")).toBe("html");
    expect(mount.getAttribute("data-available-spawn-count")).toBe("1");
    // Shipped collective panel chrome
    expect(
      screen.getByRole("heading", { name: /collective deep research/i }),
    ).toBeTruthy();
    // Spawn appears in identity row + collective checkbox list
    expect(screen.getAllByText("spn_launch_1").length).toBeGreaterThanOrEqual(1);
    first.unmount();
    // Double-run remount stable
    render(<DeepResearchSessionHost {...FIXTURE} />);
    expect(screen.getByTestId("deep-research-collective-mount")).toBeTruthy();
    expect(
      screen.getByTestId("deep-research-collective-mount").getAttribute(
        "data-available-spawn-count",
      ),
    ).toBe("1");
  });

  it("includes spawn ids from other open deep_research_session windows", () => {
    useWindows.getState().reset();
    openWindow(
      DEEP_RESEARCH_WINDOW_KIND as keyof typeof WINDOW_PAGES,
      {
        session_id: "fsess_other",
        spawn_id: "spn_other_2",
        parent_asset_id: "other-asset",
        selection_text: "other",
        status: "reserved",
        view_format: "html",
        investigation_id: "inv_other",
      },
      { id: "wdr_fsess_other", mode: "floating" },
    );
    render(
      <DeepResearchSessionHost
        {...FIXTURE}
        available_spawn_ids={["spn_extra_3"]}
      />,
    );
    const mount = screen.getByTestId("deep-research-collective-mount");
    // current + open window + extra
    expect(Number(mount.getAttribute("data-available-spawn-count"))).toBeGreaterThanOrEqual(
      2,
    );
    expect(mount.textContent).toContain("spn_launch_1");
    expect(mount.textContent).toContain("spn_other_2");
    expect(mount.textContent).toContain("spn_extra_3");
  });

  it("omits CollectiveResearchPanel when no spawn ids available", () => {
    useWindows.getState().reset();
    const { spawn_id: _s, ...noSpawn } = FIXTURE;
    render(<DeepResearchSessionHost {...noSpawn} />);
    expect(screen.queryByTestId("deep-research-collective-mount")).toBeNull();
  });

  it("kind is window-eligible in WINDOW_PAGES registry", () => {
    expect(isWindowEligible(DEEP_RESEARCH_WINDOW_KIND)).toBe(true);
    expect(WINDOW_PAGES[DEEP_RESEARCH_WINDOW_KIND]?.title).toMatch(/deep research/i);
    expect(WINDOW_PAGES[DEEP_RESEARCH_WINDOW_KIND]?.renderer).toBeTruthy();
  });

  it("openWindow registers hostable deep_research_session window with payload", () => {
    useWindows.getState().reset();
    const id = openWindow(
      DEEP_RESEARCH_WINDOW_KIND as keyof typeof WINDOW_PAGES,
      FIXTURE as unknown as Record<string, unknown>,
      { id: "wdr_fsess_launch_1", mode: "floating" },
    );
    expect(id).toBe("wdr_fsess_launch_1");
    const win = useWindows.getState().windows[id];
    expect(win).toBeTruthy();
    expect(win.kind).toBe(DEEP_RESEARCH_WINDOW_KIND);
    expect(win.payload.session_id).toBe("fsess_launch_1");
    expect(win.payload.parent_asset_id).toBe("launch-asset");
    expect(win.payload.view_format).toBe("html");
    // Second open focuses same id
    const again = openWindow(
      DEEP_RESEARCH_WINDOW_KIND as keyof typeof WINDOW_PAGES,
      FIXTURE as unknown as Record<string, unknown>,
      { id: "wdr_fsess_launch_1" },
    );
    expect(again).toBe(id);
  });
});
