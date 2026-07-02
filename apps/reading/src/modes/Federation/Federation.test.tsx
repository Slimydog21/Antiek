import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import Federation from "./index";

const apiFetchMock = vi.hoisted(() => vi.fn());

vi.mock("../../lib/api", async (orig) => {
  const actual = await orig<typeof import("../../lib/api")>();
  return {
    ...actual,
    apiFetch: apiFetchMock,
  };
});

const okJson = (body: unknown) =>
  ({
    ok: true,
    json: async () => body,
  }) as Response;

beforeEach(() => {
  apiFetchMock.mockReset();
  apiFetchMock.mockImplementation(async (path: string, init?: RequestInit) => {
    if (path === "/federation/config" && init?.method === "PUT") {
      return okJson({
        allowed_partner_substrates: [
          " partner-clean ",
          "partner-clean",
          "",
          null,
        ],
        require_opt_in_for_outbound_citations: "false",
        require_attribution_for_outbound_citations: false,
      });
    }
    return okJson({
      allowed_partner_substrates: [
        " partner-clean ",
        "partner-clean",
        " ",
        42,
      ],
      require_opt_in_for_outbound_citations: "false",
      require_attribution_for_outbound_citations: false,
    });
  });
});

afterEach(() => cleanup());

describe("Federation", () => {
  it("sanitizes federation config responses before rendering and saving", async () => {
    render(<Federation />);

    expect(await screen.findByText("partner-clean")).toBeTruthy();
    expect(screen.getAllByText("partner-clean")).toHaveLength(1);
    expect(document.body.textContent).not.toMatch(
      /partner-clean\s+partner-clean|42/,
    );

    const optIn = screen.getByLabelText(
      /Require opt-in for outbound citations/i,
    ) as HTMLInputElement;
    const attribution = screen.getByLabelText(
      /Require attribution for outbound citations/i,
    ) as HTMLInputElement;
    expect(optIn.checked).toBe(true);
    expect(attribution.checked).toBe(false);

    fireEvent.change(screen.getByPlaceholderText("e.g. partner-research-coop"), {
      target: { value: " new-partner " },
    });
    fireEvent.click(screen.getByRole("button", { name: "Add" }));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() =>
      expect(apiFetchMock).toHaveBeenCalledWith(
        "/federation/config",
        expect.objectContaining({ method: "PUT" }),
      ),
    );

    const putCall = apiFetchMock.mock.calls.find(
      ([path, init]) => path === "/federation/config" && init?.method === "PUT",
    );
    expect(JSON.parse(String(putCall?.[1]?.body))).toEqual({
      allowed_partner_substrates: ["partner-clean", "new-partner"],
      require_opt_in_for_outbound_citations: true,
      require_attribution_for_outbound_citations: false,
    });

    await screen.findByText(/Saved at/);
    expect(screen.getAllByText("partner-clean")).toHaveLength(1);
  });
});
