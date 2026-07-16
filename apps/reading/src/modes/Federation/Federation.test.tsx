import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { apiFetch } from "../../lib/api";
import Federation, { FederationPolicyView, type FederationConfig } from "./index";

vi.mock("../../lib/api", () => ({ apiFetch: vi.fn() }));
const strict: FederationConfig = { allowed_partner_substrates: [], require_opt_in_for_outbound_citations: true, require_attribution_for_outbound_citations: true };
const props = { current: strict, draft: strict, onDraftChange: vi.fn(), onRequestSave: vi.fn(), onConfirmSave: vi.fn(), onCancelConfirm: vi.fn(), onDiscard: vi.fn(), onRetry: vi.fn() };
const response = (body: unknown, ok = true) => ({ ok, json: vi.fn().mockResolvedValue(body) }) as unknown as Response;
afterEach(cleanup);

describe("Federation policy airlock", () => {
  beforeEach(() => vi.clearAllMocks());

  it("describes the bidirectional boundary without implying trust", () => {
    render(<FederationPolicyView {...props} />);
    expect(screen.getByText(/both outbound eligibility and inbound acceptance/i)).toBeTruthy();
    expect(screen.getByText(/does not register a partner, prove trust/i)).toBeTruthy();
  });

  it("rejects an invalid partner identifier locally", () => {
    render(<FederationPolicyView {...props} />);
    fireEvent.change(screen.getByLabelText(/partner substrate identifier/i), { target: { value: "../partner" } });
    fireEvent.click(screen.getByRole("button", { name: /add to draft/i }));
    expect(screen.getByRole("alert").textContent).toMatch(/letters, numbers/i);
    expect(props.onDraftChange).not.toHaveBeenCalled();
  });

  it("normalizes and adds a valid partner to the draft", () => {
    render(<FederationPolicyView {...props} />);
    fireEvent.change(screen.getByLabelText(/partner substrate identifier/i), { target: { value: " research-coop " } });
    fireEvent.click(screen.getByRole("button", { name: /add to draft/i }));
    expect(props.onDraftChange).toHaveBeenCalledWith({ ...strict, allowed_partner_substrates: ["research-coop"] });
  });

  it("shows a second seal for an expanded-risk draft", () => {
    render(<FederationPolicyView {...props} draft={{ ...strict, allowed_partner_substrates: ["research-coop"] }} confirmationOpen />);
    expect(screen.getByRole("dialog", { name: /confirm the expanded policy boundary/i })).toBeTruthy();
  });

  it("moves focus into the second seal and lets Escape close it", () => {
    render(<FederationPolicyView {...props} draft={{ ...strict, allowed_partner_substrates: ["research-coop"] }} confirmationOpen />);
    expect(document.activeElement?.textContent).toMatch(/keep reviewing/i);
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
    expect(props.onCancelConfirm).toHaveBeenCalledOnce();
  });

  it("loads a valid policy", async () => {
    vi.mocked(apiFetch).mockResolvedValue(response(strict));
    render(<Federation />);
    expect(await screen.findByText(/no partner passages are allowed/i)).toBeTruthy();
  });

  it("refuses to present a malformed successful response as policy", async () => {
    vi.mocked(apiFetch).mockResolvedValue(response({ allowed_partner_substrates: [null] }));
    render(<Federation />);
    expect((await screen.findByRole("alert")).textContent).toMatch(/policy unavailable/i);
    expect(screen.queryByText(/draft matches enforced policy/i)).toBeNull();
  });

  it("rejects duplicate partner identifiers instead of silently rewriting server state", async () => {
    vi.mocked(apiFetch).mockResolvedValue(response({ ...strict, allowed_partner_substrates: ["research-coop", "research-coop"] }));
    render(<Federation />);
    expect((await screen.findByRole("alert")).textContent).toMatch(/policy unavailable/i);
  });

  it("requires confirmation before saving a newly allowed partner", async () => {
    vi.mocked(apiFetch).mockResolvedValue(response(strict));
    render(<Federation />);
    await screen.findByText(/no partner passages are allowed/i);
    fireEvent.change(screen.getByLabelText(/partner substrate identifier/i), { target: { value: "research-coop" } });
    fireEvent.click(screen.getByRole("button", { name: /add to draft/i }));
    fireEvent.click(screen.getByRole("button", { name: /review expanded risk/i }));
    expect(screen.getByRole("dialog")).toBeTruthy();
    expect(apiFetch).toHaveBeenCalledTimes(1);
  });

  it("preserves the draft when a save is not confirmed", async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce(response(strict)).mockResolvedValueOnce(response({}, false));
    render(<Federation />);
    await screen.findByText(/no partner passages are allowed/i);
    fireEvent.change(screen.getByLabelText(/partner substrate identifier/i), { target: { value: "research-coop" } });
    fireEvent.click(screen.getByRole("button", { name: /add to draft/i }));
    fireEvent.click(screen.getByRole("button", { name: /review expanded risk/i }));
    fireEvent.click(screen.getByRole("button", { name: /confirm and save/i }));
    expect(await screen.findByText(/policy was not confirmed/i)).toBeTruthy();
    expect(screen.getByText("research-coop")).toBeTruthy();
  });

  it("accepts only a valid read-back after saving", async () => {
    const active = { ...strict, allowed_partner_substrates: ["research-coop"] };
    vi.mocked(apiFetch).mockResolvedValueOnce(response(strict)).mockResolvedValueOnce(response(active));
    render(<Federation />);
    await screen.findByText(/no partner passages are allowed/i);
    fireEvent.change(screen.getByLabelText(/partner substrate identifier/i), { target: { value: "research-coop" } });
    fireEvent.click(screen.getByRole("button", { name: /add to draft/i }));
    fireEvent.click(screen.getByRole("button", { name: /review expanded risk/i }));
    fireEvent.click(screen.getByRole("button", { name: /confirm and save/i }));
    await waitFor(() => expect(screen.getByRole("status").textContent).toMatch(/saved and read back/i));
  });
});
