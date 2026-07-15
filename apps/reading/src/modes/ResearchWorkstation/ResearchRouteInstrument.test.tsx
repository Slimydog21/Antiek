/**
 * ResearchRouteInstrument.test.tsx — component-level tests for the
 * extracted route-choice and budget-readout instrument.
 *
 * SPR-01 visual-proof: covers all four budget authority cells,
 * disabled route skipping, click/arrow/Home/End keyboard behavior,
 * focus verification, and the unavailable-route recovery copy.
 */
import { describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach } from "vitest";

import ResearchRouteInstrument from "./ResearchRouteInstrument";
import type { ResearchRouteInstrumentProps } from "./ResearchRouteInstrument";
import type { ResearchRoutePreview } from "../../lib/api";

afterEach(() => cleanup());

/* ── fixtures ────────────────────────────────────────────────────────── */

function makeCandidate(
  over: Partial<ResearchRoutePreview["candidates"][number]> &
    Pick<ResearchRoutePreview["candidates"][number], "choice_id">,
): ResearchRoutePreview["candidates"][number] {
  return {
    tier: "fast",
    configuration_fingerprint: "cfg",
    display_name: "Fast lens",
    model_policy_label: "GLM-5.2 · thinking off",
    rationale: "Exploratory work",
    ready: true,
    readiness_label: "Ready",
    ...over,
  };
}

function makeBudget(
  over: Partial<ResearchRoutePreview["budget"]>,
): ResearchRoutePreview["budget"] {
  return {
    authority: "advisory",
    daily_cap_usd: null,
    spent_usd: null,
    spent_status: "unknown",
    cap_source: null,
    notes: [],
    projection_status: "unavailable",
    projection_note: "Trajectory cost is unavailable.",
    ...over,
  };
}

function makePreview(
  candidates: ResearchRoutePreview["candidates"],
  budget?: Partial<ResearchRoutePreview["budget"]>,
): ResearchRoutePreview {
  return {
    policy_version: "research-route.v1",
    prompt_fingerprint: "fp",
    candidates,
    budget: makeBudget(budget ?? {}),
  };
}

const TWO_READY = [
  makeCandidate({
    choice_id: "rr_fast",
    tier: "fast",
    display_name: "Fast lens",
    model_policy_label: "GLM-5.2 · thinking off",
    rationale: "Exploratory work",
  }),
  makeCandidate({
    choice_id: "rr_deep",
    tier: "deep",
    display_name: "Deep lens",
    model_policy_label: "GLM-5.2 · thinking on",
    rationale: "Reasoning-heavy work",
  }),
];

const ONE_READY_ONE_DISABLED = [
  makeCandidate({
    choice_id: "rr_fast",
    tier: "fast",
    display_name: "Fast lens",
  }),
  makeCandidate({
    choice_id: "rr_deep",
    tier: "deep",
    display_name: "Deep lens",
    ready: false,
    readiness_label: "Provider unavailable",
  }),
];

const ALL_DISABLED = [
  makeCandidate({
    choice_id: "rr_deep",
    tier: "deep",
    display_name: "Deep lens",
    ready: false,
    readiness_label: "Provider unavailable",
  }),
];

function renderInstrument(overrides: Partial<ResearchRouteInstrumentProps> = {}) {
  const onSelect = vi.fn();
  const defaults: ResearchRouteInstrumentProps = {
    preview: makePreview(TWO_READY),
    selectedChoiceId: "rr_deep",
    busy: false,
    onSelect,
    ...overrides,
  };
  const result = render(<ResearchRouteInstrument {...defaults} />);
  return { ...result, ...defaults };
}

/* ── rendering ───────────────────────────────────────────────────────── */

describe("ResearchRouteInstrument — rendering", () => {
  it("renders a radiogroup with all candidates", () => {
    renderInstrument();
    const group = screen.getByRole("radiogroup", { name: "Research route" });
    expect(group).toBeTruthy();
    expect(screen.getByText("Fast lens")).toBeTruthy();
    expect(screen.getByText("Deep lens")).toBeTruthy();
  });

  it("marks the selected candidate as aria-checked", () => {
    renderInstrument({ selectedChoiceId: "rr_fast" });
    expect(
      screen.getByRole("radio", { name: /Fast lens/i }).getAttribute("aria-checked"),
    ).toBe("true");
    expect(
      screen.getByRole("radio", { name: /Deep lens/i }).getAttribute("aria-checked"),
    ).toBe("false");
  });

  it("renders the selected lens with a left-edge registration mark (border-l-sun)", () => {
    renderInstrument({ selectedChoiceId: "rr_fast" });
    const activeBtn = screen.getByRole("radio", { name: /Fast lens/i });
    expect(activeBtn.className).toContain("border-l-sun");
  });

  it("does not apply the registration mark to unselected candidates", () => {
    renderInstrument({ selectedChoiceId: "rr_fast" });
    const inactiveBtn = screen.getByRole("radio", { name: /Deep lens/i });
    expect(inactiveBtn.className).not.toContain("border-l-sun");
  });

  it("renders the projection note in a details section", () => {
    renderInstrument({
      preview: makePreview(TWO_READY, {
        projection_note: "Trajectory cost is unavailable until measured.",
      }),
    });
    fireEvent.click(screen.getByText("Route and projection details"));
    expect(
      screen.getByText(/Trajectory cost is unavailable until measured/i),
    ).toBeTruthy();
  });

  it("renders the synthesis-independently-pinned label", () => {
    renderInstrument();
    expect(screen.getByText("Synthesis independently pinned")).toBeTruthy();
  });
});

/* ── keyboard ────────────────────────────────────────────────────────── */

describe("ResearchRouteInstrument — keyboard (roving radio)", () => {
  it("ArrowRight moves selection to the next ready candidate", () => {
    const { onSelect } = renderInstrument({ selectedChoiceId: "rr_fast" });
    fireEvent.keyDown(screen.getByRole("radio", { name: /Fast lens/i }), {
      key: "ArrowRight",
    });
    expect(onSelect).toHaveBeenCalledWith(
      expect.objectContaining({ choice_id: "rr_deep" }),
    );
  });

  it("ArrowLeft moves selection to the previous ready candidate", () => {
    const { onSelect } = renderInstrument({ selectedChoiceId: "rr_deep" });
    fireEvent.keyDown(screen.getByRole("radio", { name: /Deep lens/i }), {
      key: "ArrowLeft",
    });
    expect(onSelect).toHaveBeenCalledWith(
      expect.objectContaining({ choice_id: "rr_fast" }),
    );
  });

  it("Home selects the first ready candidate", () => {
    const { onSelect } = renderInstrument({ selectedChoiceId: "rr_deep" });
    fireEvent.keyDown(screen.getByRole("radio", { name: /Deep lens/i }), {
      key: "Home",
    });
    expect(onSelect).toHaveBeenCalledWith(
      expect.objectContaining({ choice_id: "rr_fast" }),
    );
  });

  it("End selects the last ready candidate", () => {
    const { onSelect } = renderInstrument({ selectedChoiceId: "rr_fast" });
    fireEvent.keyDown(screen.getByRole("radio", { name: /Fast lens/i }), {
      key: "End",
    });
    expect(onSelect).toHaveBeenCalledWith(
      expect.objectContaining({ choice_id: "rr_deep" }),
    );
  });

  it("ArrowRight skips disabled/unavailable candidates", () => {
    const { onSelect } = renderInstrument({
      preview: makePreview(ONE_READY_ONE_DISABLED),
      selectedChoiceId: "rr_fast",
    });
    fireEvent.keyDown(screen.getByRole("radio", { name: /Fast lens/i }), {
      key: "ArrowRight",
    });
    // Wraps around to itself since the only other candidate is disabled.
    expect(onSelect).toHaveBeenCalledWith(
      expect.objectContaining({ choice_id: "rr_fast" }),
    );
  });

  it("Home skips disabled candidates and selects the first ready", () => {
    const preview = makePreview([
      makeCandidate({
        choice_id: "rr_disabled",
        tier: "deep",
        display_name: "Deep lens",
        ready: false,
        readiness_label: "Provider unavailable",
      }),
      makeCandidate({
        choice_id: "rr_fast",
        tier: "fast",
        display_name: "Fast lens",
        ready: true,
      }),
    ]);
    const { onSelect } = renderInstrument({
      preview,
      selectedChoiceId: "rr_fast",
    });
    fireEvent.keyDown(screen.getByRole("radio", { name: /Fast lens/i }), {
      key: "Home",
    });
    expect(onSelect).toHaveBeenCalledWith(
      expect.objectContaining({ choice_id: "rr_fast" }),
    );
  });

  it("clicking a candidate calls onSelect with that candidate", () => {
    const { onSelect } = renderInstrument({ selectedChoiceId: "rr_fast" });
    fireEvent.click(screen.getByRole("radio", { name: /Deep lens/i }));
    expect(onSelect).toHaveBeenCalledWith(
      expect.objectContaining({ choice_id: "rr_deep", tier: "deep" }),
    );
  });
});

/* ── focus ───────────────────────────────────────────────────────────── */

describe("ResearchRouteInstrument — focus management", () => {
  it("Home moves DOM focus to the first ready candidate", () => {
    renderInstrument({ selectedChoiceId: "rr_deep" });
    const fastBtn = screen.getByRole("radio", { name: /Fast lens/i });
    fireEvent.keyDown(screen.getByRole("radio", { name: /Deep lens/i }), {
      key: "Home",
    });
    expect(document.activeElement).toBe(fastBtn);
  });

  it("End moves DOM focus to the last ready candidate", () => {
    renderInstrument({ selectedChoiceId: "rr_fast" });
    const deepBtn = screen.getByRole("radio", { name: /Deep lens/i });
    fireEvent.keyDown(screen.getByRole("radio", { name: /Fast lens/i }), {
      key: "End",
    });
    expect(document.activeElement).toBe(deepBtn);
  });

  it("ArrowRight moves DOM focus to the next ready candidate", () => {
    renderInstrument({ selectedChoiceId: "rr_fast" });
    const deepBtn = screen.getByRole("radio", { name: /Deep lens/i });
    fireEvent.keyDown(screen.getByRole("radio", { name: /Fast lens/i }), {
      key: "ArrowRight",
    });
    expect(document.activeElement).toBe(deepBtn);
  });

  it("active candidate has tabIndex 0; inactive have tabIndex -1", () => {
    renderInstrument({ selectedChoiceId: "rr_fast" });
    expect(
      (screen.getByRole("radio", { name: /Fast lens/i }) as HTMLElement).tabIndex,
    ).toBe(0);
    expect(
      (screen.getByRole("radio", { name: /Deep lens/i }) as HTMLElement).tabIndex,
    ).toBe(-1);
  });

  it.each([null, "stale-choice"])(
    "keeps the first ready route keyboard-enterable for selection %s",
    (selectedChoiceId) => {
      renderInstrument({ selectedChoiceId });
      expect(
        (screen.getByRole("radio", { name: /Fast lens/i }) as HTMLElement)
          .tabIndex,
      ).toBe(0);
      expect(
        screen
          .getByRole("radio", { name: /Fast lens/i })
          .getAttribute("aria-checked"),
      ).toBe("false");
    },
  );
});

/* ── budget authority cells ──────────────────────────────────────────── */

describe("ResearchRouteInstrument — budget authority", () => {
  it.each([
    [
      "configured and known",
      8,
      2,
      "known",
      "ANTIEK_OPERATOR_BUDGET_USD",
      true,
      /\$2\.00 spent · \$8\.00 operator ceiling/i,
    ],
    [
      "configured and unknown",
      8,
      null,
      "unknown",
      "ANTIEK_OPERATOR_BUDGET_USD",
      false,
      /spend unknown · \$8\.00 operator ceiling/i,
    ],
    [
      "unconfigured and known",
      null,
      2,
      "known",
      null,
      false,
      /\$2\.00 daemon-tracked · no operator ceiling/i,
    ],
    [
      "unconfigured and unknown",
      null,
      null,
      "unknown",
      null,
      false,
      /spend unknown · no operator ceiling/i,
    ],
  ])(
    "renders truthful budget when %s",
    (_, cap, spent, spentStatus, capSource, hasMeter, copy) => {
      renderInstrument({
        preview: makePreview(TWO_READY, {
          daily_cap_usd: cap,
          spent_usd: spent,
          spent_status: spentStatus as "known" | "unknown",
          cap_source: capSource,
        }),
      });
      expect(screen.getByText(copy)).toBeTruthy();
      expect(screen.queryByTestId("research-budget-meter") !== null).toBe(
        hasMeter,
      );
    },
  );

  it("renders the daily ledger label", () => {
    renderInstrument();
    expect(screen.getByText("Daily ledger · advisory only")).toBeTruthy();
  });

  it("renders budget notes when present", () => {
    renderInstrument({
      preview: makePreview(TWO_READY, {
        notes: ["No operator cap is configured; the daemon default is reference-only."],
      }),
    });
    expect(
      screen.getByText(
        /No operator cap is configured; the daemon default is reference-only/i,
      ),
    ).toBeTruthy();
  });

  it.each([
    ["normal spend", 2, 8, "25%"],
    ["over-cap spend", 10, 8, "100%"],
    ["negative defensive input", -1, 8, "0%"],
  ])("clamps the meter for %s", (_, spent, cap, expectedWidth) => {
    renderInstrument({
      preview: makePreview(TWO_READY, {
        daily_cap_usd: cap,
        spent_usd: spent,
        spent_status: "known",
        cap_source: "ANTIEK_OPERATOR_BUDGET_USD",
      }),
    });
    const fill = screen.getByTestId("research-budget-meter").firstElementChild;
    expect((fill as HTMLElement).style.width).toBe(expectedWidth);
  });
});

/* ── unavailable route ───────────────────────────────────────────────── */

describe("ResearchRouteInstrument — unavailable route", () => {
  it("shows recovery fallback when all routes are unavailable", () => {
    renderInstrument({
      preview: makePreview(ALL_DISABLED),
    });
    expect(
      screen.getByText(/preferred drivers are unavailable/i),
    ).toBeTruthy();
  });

  it("does not show the fallback when at least one route is ready", () => {
    renderInstrument();
    expect(
      screen.queryByText(/preferred drivers are unavailable/i),
    ).toBeNull();
  });

  it("renders disabled candidates with reduced opacity", () => {
    renderInstrument({
      preview: makePreview(ONE_READY_ONE_DISABLED),
    });
    const disabledBtn = screen.getByRole("radio", {
      name: /Deep lens/i,
    }) as HTMLButtonElement;
    expect(disabledBtn.disabled).toBe(true);
    expect(disabledBtn.className).toContain("disabled:opacity-60");
  });

  it("does not present a remembered unavailable route as selected", () => {
    renderInstrument({
      preview: makePreview(ALL_DISABLED),
      selectedChoiceId: "rr_deep",
    });
    const unavailable = screen.getByRole("radio", { name: /Deep lens/i });
    expect(unavailable.getAttribute("aria-checked")).toBe("false");
    expect(unavailable.className).not.toContain("border-l-sun");
  });
});

/* ── busy state ──────────────────────────────────────────────────────── */

describe("ResearchRouteInstrument — busy state", () => {
  it("disables all candidates when busy", () => {
    renderInstrument({ busy: true });
    expect(
      (screen.getByRole("radio", { name: /Fast lens/i }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
    expect(
      (screen.getByRole("radio", { name: /Deep lens/i }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
  });
});
