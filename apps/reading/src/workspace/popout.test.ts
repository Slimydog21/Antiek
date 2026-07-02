import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { openPopoutFor, popoutWindowName } from "./popout";
import { useWorkspace } from "./WorkspaceStore";

const s = () => useWorkspace.getState();

beforeEach(() => {
  s().reset();
  vi.stubGlobal("BroadcastChannel", undefined);
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  s().reset();
});

describe("workspace popout", () => {
  it("sanitizes OS window names separately from encoded panel routes", () => {
    expect(popoutWindowName("Lightbox:https://img.example/a b.png")).toBe(
      "antiek_popout_Lightbox_https_img_example_a_b_png",
    );
    expect(popoutWindowName("///")).toBe("antiek_popout_panel");
  });

  it("opens an encoded local panel route with a sanitized window name", () => {
    const panelId = "Lightbox:https://img.example/a b.png";
    s().open("Lightbox", { src: "https://img.example/a b.png" }, { id: panelId });
    const open = vi.spyOn(window, "open").mockReturnValue({} as Window);

    openPopoutFor(panelId);

    expect(open).toHaveBeenCalledTimes(1);
    const [url, name, features] = open.mock.calls[0];
    expect(url).toBe(`/_panel/${encodeURIComponent(panelId)}`);
    expect(name).toBe("antiek_popout_Lightbox_https_img_example_a_b_png");
    expect(features).toContain("popup");
    expect(s().panels[panelId].mode).toBe("popout");
  });
});
