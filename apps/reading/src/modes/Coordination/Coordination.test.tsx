import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { apiFetch } from "../../lib/api";
import Coordination from "./index";

vi.mock("../../lib/api", () => ({
  apiFetch: vi.fn(),
}));

const apiFetchMock = vi.mocked(apiFetch);

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("Coordination", () => {
  it("sanitizes gate and roadmap API responses before rendering", async () => {
    apiFetchMock.mockImplementation(async (input) => {
      const path = String(input);
      if (path === "/coordination/gates") {
        return {
          ok: true,
          json: async () => ({
            source_path: " docs/operator_gate_actions.md ",
            gates: [
              {
                gate_id: " G2 ",
                title: " ",
                status: "unexpected",
                status_raw: " open until counsel review ",
                is_provisional: "yes",
                owner: " Legal ",
                closure_record: " ",
                impacts: [
                  {
                    product: "read",
                    effect: " blocks publisher payout ",
                  },
                  {
                    product: "unknown",
                    effect: "Skipped impact",
                  },
                ],
              },
              {
                gate_id: " ",
                title: "Skipped gate",
              },
            ],
          }),
        } as Response;
      }
      return {
        ok: true,
        json: async () => ({
          total_sprints: "45.9",
          superseded_count: "6",
          superseded_note: " shell superseded ",
          reconciliation: " reconciled count ",
          critical_path: [" drw:1 ", " "],
          rosters: [
            {
              spec: " read ",
              label: " Read ",
              directory: " read ",
              count: "2.9",
              sprints: [
                {
                  spec: "read",
                  spec_label: "Read",
                  sprint: "2",
                  slug: " library-browse ",
                  node_id: " read:2 ",
                  status: " ",
                  on_critical_path: "yes",
                  blocked_on: [" drw:10 ", " "],
                  unblocked: false,
                },
                {
                  node_id: " ",
                  slug: "Skipped sprint",
                },
              ],
            },
            {
              spec: " ",
              label: "Skipped roster",
            },
          ],
          unblocked_now: [" read:2 ", " "],
          substrate_layers: [
            {
              name: " db lock ",
              owner: " runtime/db_lock.py ",
              status: " hardened ",
            },
            {
              name: " ",
              owner: "Skipped layer",
            },
          ],
        }),
      } as Response;
    });

    render(<Coordination />);

    await screen.findByText("reconciled count");
    expect(screen.getAllByText("G2").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("open")).toBeTruthy();
    expect(screen.getByText("open until counsel review")).toBeTruthy();
    expect(screen.getByText("blocks publisher payout")).toBeTruthy();
    expect(screen.queryByText("Skipped gate")).toBeNull();
    expect(screen.queryByText("Skipped impact")).toBeNull();

    expect(screen.getByText("library browse")).toBeTruthy();
    expect(screen.getByText("waits on drw:10")).toBeTruthy();
    expect(screen.getByText("db lock")).toBeTruthy();
    expect(document.body.textContent).not.toMatch(
      /Skipped sprint|Skipped roster|Skipped layer/,
    );
  });
});
