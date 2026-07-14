import { useLayoutEffect } from "react";
import { act, cleanup, fireEvent, render } from "@testing-library/react";
import { MemoryRouter, useNavigate } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const fishingFlag = vi.hoisted(() => ({ enabled: true }));
vi.mock("./iceFishingFlags", () => ({
  get wernerIceFishingCursor() {
    return fishingFlag.enabled;
  },
}));

import { StationInstrumentAtlas } from "./StationInstrumentAtlas.stories";
import { WernerIceCursorShell } from "./WernerIceCursorShell";
import {
  acquireStationInstrumentSuspension,
  useStationInstrumentSuspended,
} from "./stationInstrumentSuspension";

function TransitionHarness() {
  const navigate = useNavigate();
  return (
    <>
      <button type="button" onClick={() => navigate("/speak/project-7")}>
        Speak
      </button>
      <button type="button" onClick={() => navigate("/brainstorm")}>
        Research
      </button>
      <button type="button" onClick={() => navigate("/not-a-route")}>
        Unknown
      </button>
      <WernerIceCursorShell />
    </>
  );
}

function LayoutPhaseCursorProbe({
  onLayout,
}: {
  onLayout: (nativeCursorHidden: boolean) => void;
}) {
  useStationInstrumentSuspended();
  useLayoutEffect(() => {
    onLayout(
      document.documentElement.classList.contains(
        "werner-ice-cursor-hidden",
      ),
    );
  });
  return null;
}

beforeEach(() => {
  fishingFlag.enabled = true;
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    configurable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
    })),
  });
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  document.documentElement.classList.remove("werner-ice-cursor-hidden");
  document.documentElement.classList.remove("werner-writing-nib-active");
  document.documentElement.classList.remove("werner-speaking-resonance-active");
});

describe("Werner cursor shell route transitions", () => {
  it("returns pointer authority to a focused game and restores the route instrument", () => {
    const layoutStates: boolean[] = [];
    const { getByTestId, queryByTestId } = render(
      <MemoryRouter initialEntries={["/brainstorm"]}>
        <WernerIceCursorShell />
        <LayoutPhaseCursorProbe
          onLayout={(nativeCursorHidden) => layoutStates.push(nativeCursorHidden)}
        />
      </MemoryRouter>,
    );
    expect(getByTestId("research-lens-cursor")).toBeTruthy();
    expect(document.documentElement.classList).toContain(
      "werner-ice-cursor-hidden",
    );

    let release = () => {};
    act(() => {
      release = acquireStationInstrumentSuspension("test-game");
    });
    expect(queryByTestId("research-lens-cursor")).toBeNull();
    expect(document.documentElement.classList).not.toContain(
      "werner-ice-cursor-hidden",
    );
    expect(layoutStates.at(-1)).toBe(false);

    act(release);
    expect(getByTestId("research-lens-cursor")).toBeTruthy();
    expect(document.documentElement.classList).toContain(
      "werner-ice-cursor-hidden",
    );
    expect(layoutStates.at(-1)).toBe(true);
  });

  it("keeps exactly one workflow instrument and cleans activity markers", () => {
    const { container, getByRole, getByTestId, queryByTestId, unmount } =
      render(
        <MemoryRouter initialEntries={["/write/draft-4"]}>
          <TransitionHarness />
        </MemoryRouter>,
      );

    expect(getByTestId("writing-nib-cursor")).toBeTruthy();
    expect(queryByTestId("speaking-resonance-cursor")).toBeNull();
    expect(document.documentElement.classList).toContain(
      "werner-writing-nib-active",
    );
    expect(document.documentElement.classList).not.toContain(
      "werner-speaking-resonance-active",
    );

    fireEvent.click(getByRole("button", { name: "Speak" }));
    expect(queryByTestId("writing-nib-cursor")).toBeNull();
    expect(getByTestId("speaking-resonance-cursor")).toBeTruthy();
    expect(document.documentElement.classList).not.toContain(
      "werner-writing-nib-active",
    );
    expect(document.documentElement.classList).toContain(
      "werner-speaking-resonance-active",
    );

    fireEvent.click(getByRole("button", { name: "Research" }));
    expect(queryByTestId("speaking-resonance-cursor")).toBeNull();
    expect(getByTestId("research-lens-cursor")).toBeTruthy();
    expect(document.documentElement.classList).not.toContain(
      "werner-writing-nib-active",
    );
    expect(document.documentElement.classList).not.toContain(
      "werner-speaking-resonance-active",
    );

    fireEvent.click(getByRole("button", { name: "Unknown" }));
    expect(queryByTestId("research-lens-cursor")).toBeNull();
    expect(container.querySelector(".werner-ice-bait")).toBeTruthy();
    expect(document.documentElement.classList).toContain(
      "werner-ice-cursor-hidden",
    );

    unmount();
    expect(document.documentElement.classList).not.toContain(
      "werner-ice-cursor-hidden",
    );
  });

  it("preserves the native cursor on an unknown route when fishing is disabled", () => {
    fishingFlag.enabled = false;

    const { container } = render(
      <MemoryRouter initialEntries={["/not-a-route"]}>
        <WernerIceCursorShell />
      </MemoryRouter>,
    );

    expect(container.querySelector(".werner-ice-bait")).toBeNull();
    expect(document.documentElement.classList).not.toContain(
      "werner-ice-cursor-hidden",
    );
  });

  it("selects exactly one atlas instrument and cleans activity markers", () => {
    vi.useFakeTimers();
    const { container, getByRole, getByTestId, queryByTestId } = render(
      <MemoryRouter>
        <StationInstrumentAtlas />
      </MemoryRouter>,
    );
    const instrumentCount = () =>
      container.querySelectorAll(
        '[data-testid="research-lens-cursor"], [data-testid="writing-nib-cursor"], [data-testid="speaking-resonance-cursor"], .werner-ice-bait',
      ).length;

    expect(getByTestId("research-lens-cursor")).toBeTruthy();
    expect(instrumentCount()).toBe(1);

    fireEvent.click(getByRole("button", { name: /writing-nib/ }));
    expect(getByTestId("writing-nib-cursor")).toBeTruthy();
    expect(instrumentCount()).toBe(1);
    expect(document.documentElement.classList).toContain(
      "werner-writing-nib-active",
    );

    fireEvent.click(getByRole("button", { name: /speaking-resonance/ }));
    expect(queryByTestId("writing-nib-cursor")).toBeNull();
    expect(getByTestId("speaking-resonance-cursor")).toBeTruthy();
    expect(instrumentCount()).toBe(1);
    expect(document.documentElement.classList).not.toContain(
      "werner-writing-nib-active",
    );
    expect(document.documentElement.classList).toContain(
      "werner-speaking-resonance-active",
    );

    const mascot = getByTestId("penguin-mascot");
    const mascotRect = vi
      .spyOn(mascot, "getBoundingClientRect")
      .mockReturnValue({
        x: 88,
        y: 640,
        left: 88,
        top: 640,
        right: 152,
        bottom: 704,
        width: 64,
        height: 64,
        toJSON: () => ({}),
      });
    fireEvent.click(getByRole("button", { name: /ice-fishing/ }));
    act(() => {
      window.dispatchEvent(
        new PointerEvent("pointermove", {
          clientX: 700,
          clientY: 420,
          bubbles: true,
        }),
      );
      vi.advanceTimersByTime(64);
    });
    expect(queryByTestId("speaking-resonance-cursor")).toBeNull();
    expect(container.querySelector(".werner-ice-bait")).toBeTruthy();
    expect(mascotRect).toHaveBeenCalled();
    expect(
      container
        .querySelector('path[stroke-opacity="0.4"][stroke-width="1"]')
        ?.getAttribute("d"),
    ).toMatch(/\S/);
    expect(instrumentCount()).toBe(1);
    expect(document.documentElement.classList).not.toContain(
      "werner-speaking-resonance-active",
    );
  });

  it("keeps fishing absent in the atlas when its feature flag is disabled", () => {
    fishingFlag.enabled = false;
    const { container, getByRole, getByText } = render(
      <MemoryRouter>
        <StationInstrumentAtlas />
      </MemoryRouter>,
    );

    fireEvent.click(getByRole("button", { name: /ice-fishing/ }));

    expect(container.querySelector(".werner-ice-bait")).toBeNull();
    expect(document.documentElement.classList).not.toContain(
      "werner-ice-cursor-hidden",
    );
    expect(
      getByText("Native cursor preserved · custom instrument unavailable"),
    ).toBeTruthy();
  });

  it("keeps the native cursor and mounts no atlas instrument under reduced motion", () => {
    vi.mocked(window.matchMedia).mockImplementation((query: string) => ({
      matches: query === "(prefers-reduced-motion: reduce)",
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }));

    const { queryByTestId } = render(
      <MemoryRouter>
        <StationInstrumentAtlas />
      </MemoryRouter>,
    );

    expect(queryByTestId("research-lens-cursor")).toBeNull();
    expect(document.documentElement.classList).not.toContain(
      "werner-ice-cursor-hidden",
    );
  });
});
