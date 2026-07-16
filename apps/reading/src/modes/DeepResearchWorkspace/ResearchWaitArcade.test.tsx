import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import { createRef, useEffect, useRef } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const createCartridge = vi.hoisted(() => vi.fn());
const teardown = vi.hoisted(() => vi.fn());
const receivedSceneArt = vi.hoisted(() => vi.fn());

vi.mock("./ResearchWaitArcadeGame", () => ({
  default: ({
    game,
    sceneArtSrc,
  }: {
    game: "clam-catcher" | "ice-fishing" | "zombies";
    sceneArtSrc: string;
  }) => {
    createCartridge(game);
    receivedSceneArt(sceneArtSrc);
    const canvasRef = useRef<HTMLCanvasElement>(null);
    useEffect(() => {
      canvasRef.current?.focus();
    }, []);
    return (
      <canvas
        ref={canvasRef}
        data-testid="research-wait-arcade-canvas"
        role="application"
        tabIndex={0}
      />
    );
  },
}));

import ResearchWaitArcade from "./ResearchWaitArcade";
import { isStationInstrumentSuspended } from "../../werner/stationInstrumentSuspension";

function cartridge() {
  return {
    id: "paperclip-zombies",
    meta: { title: "Paperclip Zombies", blurb: "", style: "zombies-arcade" },
    init: vi.fn(),
    update: vi.fn(),
    render: vi.fn(),
    teardown,
  };
}

function Host({ episodeId = "session:1", after = 8_000 }) {
  const returnFocusRef = createRef<HTMLHeadingElement>();
  return (
    <>
      <h2 ref={returnFocusRef} tabIndex={-1}>
        Research monitor
      </h2>
      <ResearchWaitArcade
        episodeId={episodeId}
        activeResearchCount={2}
        offerAfterMs={after}
        returnFocusRef={returnFocusRef}
      />
    </>
  );
}

function ConditionalHost({ visible }: { visible: boolean }) {
  const returnFocusRef = useRef<HTMLHeadingElement>(null);
  return (
    <>
      <h2 ref={returnFocusRef} tabIndex={-1}>
        Research monitor
      </h2>
      {visible && (
        <ResearchWaitArcade
          episodeId="session:terminal"
          activeResearchCount={1}
          offerAfterMs={0}
          returnFocusRef={returnFocusRef}
        />
      )}
    </>
  );
}

function LeavingHost({ visible }: { visible: boolean }) {
  const returnFocusRef = useRef<HTMLHeadingElement>(null);
  return (
    <>
      <h2 ref={returnFocusRef} tabIndex={-1}>
        Research monitor
      </h2>
      <button type="button">Redirect research</button>
      {visible && (
        <ResearchWaitArcade
          episodeId="session:1"
          activeResearchCount={1}
          offerAfterMs={0}
          returnFocusRef={returnFocusRef}
        />
      )}
    </>
  );
}

beforeEach(() => {
  vi.useFakeTimers();
  createCartridge.mockReset();
  teardown.mockReset();
  receivedSceneArt.mockReset();
  createCartridge.mockImplementation(cartridge);
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("ResearchWaitArcade", () => {
  it("does not construct or flash a game before the exact offer threshold", () => {
    render(<Host after={8_000} />);
    act(() => vi.advanceTimersByTime(7_999));
    expect(screen.queryByTestId("research-wait-arcade")).toBeNull();
    expect(createCartridge).not.toHaveBeenCalled();

    act(() => vi.advanceTimersByTime(1));
    expect(
      screen.getByRole("button", { name: "Play while waiting" }),
    ).toBeTruthy();
    expect(createCartridge).not.toHaveBeenCalled();
  });

  it("keeps the optional arcade hidden for reduced-motion readers", () => {
    const returnFocusRef = createRef<HTMLElement>();
    render(
      <ResearchWaitArcade
        episodeId="session:reduced"
        activeResearchCount={2}
        offerAfterMs={0}
        returnFocusRef={returnFocusRef}
        reducedMotion
      />,
    );
    act(() => vi.runOnlyPendingTimers());
    expect(screen.queryByTestId("research-wait-arcade")).toBeNull();
    expect(createCartridge).not.toHaveBeenCalled();
  });

  it("constructs only after explicit Play and does not focus before activation", async () => {
    render(<Host after={0} />);
    act(() => vi.runOnlyPendingTimers());
    expect(document.activeElement).toBe(document.body);
    await act(async () => {
      fireEvent.click(
        screen.getByRole("button", { name: "Play while waiting" }),
      );
    });
    const canvas = screen.getByTestId("research-wait-arcade-canvas");
    expect(createCartridge).toHaveBeenCalledWith("zombies");
    expect(canvas).toBe(document.activeElement);
    expect(isStationInstrumentSuspended()).toBe(true);
  });

  it("stamps Flipbook invent reframe on wait-arcade cartridge invent art", () => {
    render(<Host after={0} />);
    act(() => vi.runOnlyPendingTimers());
    for (const id of ["ice-fishing", "clam-catcher", "zombies"] as const) {
      const art = screen.getByTestId(
        `research-wait-${id}-living-tv-art`,
      ) as HTMLImageElement;
      expect(art.className).toMatch(/antiek-living-tv-invent/);
      expect(art.getAttribute("src")).toBeTruthy();
    }
  });

  it("offers all cartridges without constructing any and launches the explicit choice", async () => {
    render(<Host after={0} />);
    act(() => vi.runOnlyPendingTimers());

    const zombies = screen.getByRole("radio", { name: /Paperclip Zombies/ });
    const fishing = screen.getByRole("radio", { name: /Ice Fishing/ });
    const clams = screen.getByRole("radio", { name: /Clam Catcher/ });
    expect((zombies as HTMLInputElement).checked).toBe(true);
    expect((fishing as HTMLInputElement).checked).toBe(false);
    expect((clams as HTMLInputElement).checked).toBe(false);
    expect(createCartridge).not.toHaveBeenCalled();

    fireEvent.click(clams);
    expect((clams as HTMLInputElement).checked).toBe(true);
    expect(createCartridge).not.toHaveBeenCalled();

    await act(async () => {
      fireEvent.click(
        screen.getByRole("button", { name: "Play while waiting" }),
      );
    });
    expect(createCartridge).toHaveBeenCalledWith("clam-catcher");
    expect(screen.getByText("Clam Catcher")).toBeTruthy();
  });

  it.each(["Escape", "button"])(
    "exits with %s and restores focus to the visible Play control",
    (exitKind) => {
      render(<Host after={0} />);
      act(() => vi.runOnlyPendingTimers());
      fireEvent.click(
        screen.getByRole("button", { name: "Play while waiting" }),
      );
      if (exitKind === "Escape") {
        fireEvent.keyDown(screen.getByTestId("research-wait-arcade-canvas"), {
          key: "Escape",
        });
      } else {
        fireEvent.click(screen.getByRole("button", { name: "Exit game" }));
      }
      act(() => vi.runAllTicks());
      expect(screen.queryByTestId("research-wait-arcade-canvas")).toBeNull();
      expect(screen.getByRole("button", { name: "Play while waiting" })).toBe(
        document.activeElement,
      );
      expect(isStationInstrumentSuspended()).toBe(false);
    },
  );

  it("resets opt-in and timer when the episode identity changes", () => {
    const { rerender } = render(<Host episodeId="same:1" after={0} />);
    act(() => vi.runOnlyPendingTimers());
    fireEvent.click(screen.getByRole("button", { name: "Play while waiting" }));
    expect(createCartridge).toHaveBeenCalledTimes(1);

    rerender(<Host episodeId="same:2" after={8_000} />);
    expect(isStationInstrumentSuspended()).toBe(false);
    expect(screen.queryByTestId("research-wait-arcade")).toBeNull();
    expect(screen.queryByTestId("research-wait-arcade-canvas")).toBeNull();
    act(() => vi.advanceTimersByTime(8_000));
    expect(
      screen.getByRole("button", { name: "Play while waiting" }),
    ).toBeTruthy();
  });

  it("creates a fresh cartridge across repeated Play and Exit cycles", () => {
    render(<Host after={0} />);
    act(() => vi.runOnlyPendingTimers());
    fireEvent.click(screen.getByRole("button", { name: "Play while waiting" }));
    fireEvent.click(screen.getByRole("button", { name: "Exit game" }));
    act(() => vi.runAllTicks());
    fireEvent.click(screen.getByRole("button", { name: "Play while waiting" }));
    expect(createCartridge).toHaveBeenCalledTimes(2);
  });

  it("returns focus to the stable monitor heading when completion removes focused gameplay", async () => {
    const { rerender } = render(<ConditionalHost visible />);
    act(() => vi.runOnlyPendingTimers());
    await act(async () => {
      fireEvent.click(
        screen.getByRole("button", { name: "Play while waiting" }),
      );
    });
    rerender(<ConditionalHost visible={false} />);
    expect(isStationInstrumentSuspended()).toBe(false);
    expect(screen.getByRole("heading", { name: "Research monitor" })).toBe(
      document.activeElement,
    );
  });

  it("does not steal focus when completion follows a deliberate workspace move", () => {
    const { rerender } = render(<LeavingHost visible />);
    act(() => vi.runOnlyPendingTimers());
    fireEvent.click(screen.getByRole("button", { name: "Play while waiting" }));
    const redirect = screen.getByRole("button", { name: "Redirect research" });
    redirect.focus();

    rerender(<LeavingHost visible={false} />);

    expect(redirect).toBe(document.activeElement);
  });

  it("does not capture Escape from a workspace input outside the game", () => {
    render(
      <div>
        <input aria-label="redirect research" />
        <Host after={0} />
      </div>,
    );
    act(() => vi.runOnlyPendingTimers());
    fireEvent.click(screen.getByRole("button", { name: "Play while waiting" }));
    const input = screen.getByRole("textbox", { name: "redirect research" });
    input.focus();
    fireEvent.keyDown(input, { key: "Escape" });
    expect(screen.getByTestId("research-wait-arcade-canvas")).toBeTruthy();
  });

  it("exposes responsive containment and three decorative project assets", () => {
    render(<Host after={0} />);
    act(() => vi.runOnlyPendingTimers());
    const host = screen.getByTestId("research-wait-arcade");
    expect(host.className).toContain("research-wait-arcade");
    const images = [...host.querySelectorAll("img")];
    expect(images).toHaveLength(3);
    expect(images.every((image) => image.alt === "")).toBe(true);
    expect(
      images.every((image) => image.getAttribute("aria-hidden") === "true"),
    ).toBe(true);
    expect(
      images.every((image) => {
        const src = image.getAttribute("src") ?? "";
        // All three wait-arcade cards use session brand PNGs (alpha-gated).
        return src.startsWith("/src/brand/werner/poses/session/");
      }),
    ).toBe(true);
    // Session product key art for all Club-Penguin-style wait games + zombies.
    expect(
      images.some((image) =>
        (image.getAttribute("src") ?? "").includes(
          "werner_igloo_ice_arcade_cursor_session_v1",
        ),
      ),
    ).toBe(true);
    expect(
      images.some((image) =>
        (image.getAttribute("src") ?? "").includes("werner_paperclip_zombies_arcade_session_v1"),
      ),
    ).toBe(true);
    expect(
      images.some((image) =>
        (image.getAttribute("src") ?? "").includes(
          "werner_clam_catcher_cursor_session_v1",
        ),
      ),
    ).toBe(true);
  });

  it("propagates the selected art to the playing scene-continuity layer", async () => {
    render(<Host after={0} />);
    act(() => vi.runOnlyPendingTimers());
    fireEvent.click(screen.getByRole("radio", { name: /Ice Fishing/ }));
    await act(async () => {
      fireEvent.click(
        screen.getByRole("button", { name: "Play while waiting" }),
      );
    });
    expect(receivedSceneArt).toHaveBeenCalledTimes(1);
    expect(receivedSceneArt.mock.calls[0]?.[0]).toContain(
      "werner_igloo_ice_arcade_cursor_session_v1",
    );
  });
});
