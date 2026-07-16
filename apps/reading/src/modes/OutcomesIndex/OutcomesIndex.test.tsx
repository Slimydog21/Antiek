import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import {
  MemoryRouter,
  Route,
  Routes,
  useLocation,
} from "react-router-dom";

const apiFetchMock = vi.hoisted(() => vi.fn());
vi.mock("../../lib/api", async (original) => ({
  ...(await original<typeof import("../../lib/api")>()),
  apiFetch: apiFetchMock,
}));

import OutcomesIndex, {
  CalibrationObservatoryFrame,
  type OutcomeRow,
} from "./index";

afterEach(() => {
  cleanup();
  apiFetchMock.mockReset();
});

function LocationProbe() {
  return <output data-testid="location">{useLocation().pathname}</output>;
}

function renderIndex() {
  return render(
    <MemoryRouter initialEntries={["/outcomes"]}>
      <Routes>
        <Route
          path="*"
          element={
            <>
              <OutcomesIndex />
              <LocationProbe />
            </>
          }
        />
      </Routes>
    </MemoryRouter>,
  );
}

const success = (outcomes: unknown[] = []) => ({
  ok: true,
  status: 200,
  json: async () => ({ outcomes }),
});

describe("OutcomesIndex — Calibration Observatory", () => {
  it("requests the exact blank-filter query", async () => {
    apiFetchMock.mockResolvedValue(success());
    renderIndex();
    await waitFor(() => expect(apiFetchMock).toHaveBeenCalledOnce());
    expect(apiFetchMock).toHaveBeenCalledWith("/outcomes?limit=200");
  });

  it("trims and encodes the observer before limit in the exact query", async () => {
    apiFetchMock.mockResolvedValue(success());
    renderIndex();
    await waitFor(() => expect(apiFetchMock).toHaveBeenCalledOnce());
    fireEvent.change(screen.getByLabelText("Filter by observer"), {
      target: { value: "  field notes/reviewer  " },
    });
    await waitFor(() => expect(apiFetchMock).toHaveBeenCalledTimes(2));
    expect(apiFetchMock.mock.calls[1][0]).toBe(
      "/outcomes?observer=field+notes%2Freviewer&limit=200",
    );
  });

  it("renders the preserved row facts", async () => {
    apiFetchMock.mockResolvedValue(
      success([
        {
          outcome_id: "outcome-1234567890",
          synthesis_id: "synthesis-one",
          observer: "__operator__",
          observed_at: "2026-07-14",
        },
      ]),
    );
    renderIndex();
    expect(await screen.findByText("synthesis-one")).toBeTruthy();
    expect(screen.getByText("2026-07-14 · __operator__")).toBeTruthy();
    expect(screen.getByText("outcome-1234567890")).toBeTruthy();
  });

  it("keeps a long observer identity complete in the record", async () => {
    const observer = "__operator_with_a_deliberately_long_identity__";
    apiFetchMock.mockResolvedValue(
      success([
        {
          outcome_id: "outcome-long-observer",
          synthesis_id: "synthesis-long-observer",
          observer,
          observed_at: "2026-07-16",
        },
      ]),
    );
    renderIndex();
    expect(await screen.findByText(`2026-07-16 · ${observer}`)).toBeTruthy();
  });

  it("actually navigates to the encoded synthesis route on row click", async () => {
    apiFetchMock.mockResolvedValue(
      success([
        {
          outcome_id: "outcome-one",
          synthesis_id: "spaces/and slashes",
          observer: "__operator__",
          observed_at: "2026-07-14",
        },
      ]),
    );
    renderIndex();
    fireEvent.click(
      await screen.findByRole("button", { name: "spaces/and slashes" }),
    );
    expect(screen.getByTestId("location").textContent).toBe(
      "/outcomes/spaces%2Fand%20slashes",
    );
  });

  it("explains an empty filtered record without implementation or route copy", async () => {
    apiFetchMock.mockResolvedValue(success());
    renderIndex();
    expect(await screen.findByText("No judgments match this observer yet.")).toBeTruthy();
    expect(screen.getByText(/validated, falsified, or indeterminate/)).toBeTruthy();
    expect(screen.queryByText(/Phase 8|master-spec|\/outcomes\//i)).toBeNull();
  });

  it("keeps rejected exceptions private and offers retry", async () => {
    apiFetchMock.mockRejectedValue(new Error("GET /outcomes HTTP 500 secret"));
    renderIndex();
    expect((await screen.findByRole("alert")).textContent).toContain(
      "Outcomes could not be loaded. Your research record is unchanged.",
    );
    expect(screen.queryByText(/HTTP 500|GET \/outcomes|secret/)).toBeNull();
    expect(screen.getByRole("button", { name: "Try again" })).toBeTruthy();
  });

  it("keeps non-ok response details private", async () => {
    apiFetchMock.mockResolvedValue({ ok: false, status: 403 });
    renderIndex();
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(screen.queryByText(/403|request failed/i)).toBeNull();
  });

  it("retries the same filter after failure", async () => {
    apiFetchMock
      .mockRejectedValueOnce(new Error("private"))
      .mockResolvedValueOnce(success());
    renderIndex();
    fireEvent.click(await screen.findByRole("button", { name: "Try again" }));
    await waitFor(() => expect(apiFetchMock).toHaveBeenCalledTimes(2));
    expect(apiFetchMock.mock.calls[1][0]).toBe("/outcomes?limit=200");
  });

  it("does not let an older observer response overwrite the active filter", async () => {
    let resolveFirst!: (value: ReturnType<typeof success>) => void;
    const first = new Promise<ReturnType<typeof success>>((resolve) => {
      resolveFirst = resolve;
    });
    apiFetchMock
      .mockReturnValueOnce(first)
      .mockResolvedValueOnce(
        success([
          {
            outcome_id: "new-outcome",
            synthesis_id: "new-filter-result",
            observer: "new",
            observed_at: "2026-07-16",
          },
        ]),
      );
    renderIndex();
    fireEvent.change(screen.getByLabelText("Filter by observer"), {
      target: { value: "new" },
    });
    expect(await screen.findByText("new-filter-result")).toBeTruthy();
    resolveFirst(
      success([
        {
          outcome_id: "stale-outcome",
          synthesis_id: "stale-filter-result",
          observer: "old",
          observed_at: "2026-07-15",
        },
      ]),
    );
    await Promise.resolve();
    expect(screen.queryByText("stale-filter-result")).toBeNull();
    expect(screen.getByText("new-filter-result")).toBeTruthy();
  });

  it("marks the generated environment as decorative and inert", async () => {
    apiFetchMock.mockResolvedValue(success());
    const { container } = renderIndex();
    await screen.findByText("No judgments match this observer yet.");
    const image = container.querySelector(".calibration-observatory > img");
    expect(image?.getAttribute("alt")).toBe("");
    expect(image?.getAttribute("aria-hidden")).toBe("true");
    expect(image?.getAttribute("draggable")).toBe("false");
  });

  it("does not nest a main landmark inside AppShell's route landmark", async () => {
    apiFetchMock.mockResolvedValue(success());
    const { container } = renderIndex();
    await screen.findByText("No judgments match this observer yet.");
    expect(container.querySelectorAll("main")).toHaveLength(0);
  });

  it("contains and scrolls a long record inside a reduced shell-height boundary", () => {
    const rows: OutcomeRow[] = Array.from({ length: 30 }, (_, index) => ({
      outcome_id: `outcome-${index}`,
      synthesis_id: `synthesis-${index}`,
      observer: "__operator__",
      observed_at: "2026-07-16",
    }));
    const { container } = render(
      <div style={{ height: "320px", width: "768px" }}>
        <CalibrationObservatoryFrame
          rows={rows}
          loading={false}
          error={false}
          observerFilter=""
          onObserverFilterChange={() => undefined}
          onRetry={() => undefined}
          onOpenSynthesis={() => undefined}
          fixture
        />
      </div>,
    );
    const surface = container.querySelector(
      ".calibration-observatory",
    ) as HTMLElement;
    expect(surface.classList.contains("calibration-observatory")).toBe(true);
    expect((surface.parentElement as HTMLElement).style.height).toBe("320px");
    expect(surface.getAttribute("style")).toBeNull();
    expect(container.querySelectorAll("main")).toHaveLength(0);
  });
});
