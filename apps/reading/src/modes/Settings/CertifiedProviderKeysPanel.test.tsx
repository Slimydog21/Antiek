import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import {
  fetchCertifiedProviderCredentials,
  putCertifiedProviderCredential,
} from "../../api/settingsModels";
import CertifiedProviderKeysPanel from "./CertifiedProviderKeysPanel";

const SECRET = "sk-certified-secret-000111222333";

vi.mock("../../api/settingsModels", () => ({
  fetchCertifiedProviderCredentials: vi.fn(),
  putCertifiedProviderCredential: vi.fn(),
}));

const inventory = {
  providers: [
    { provider_handle: "anthropic" as const, key_present: false },
    { provider_handle: "deepseek" as const, key_present: true },
    { provider_handle: "hermes" as const, key_present: false },
    { provider_handle: "openrouter" as const, key_present: false },
    { provider_handle: "xiaomi" as const, key_present: true },
    { provider_handle: "zai" as const, key_present: true },
  ],
  byot_only: false,
};

describe("CertifiedProviderKeysPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchCertifiedProviderCredentials).mockResolvedValue(inventory);
    vi.mocked(putCertifiedProviderCredential).mockResolvedValue({
      provider_handle: "deepseek",
      key_present: true,
      registered_providers: ["deepseek"],
      source: "encrypted_byok_store",
    });
  });

  afterEach(cleanup);

  it("removes the process-wide surface for a non-operator 403", async () => {
    vi.mocked(fetchCertifiedProviderCredentials).mockResolvedValue(null);
    const { container } = render(<CertifiedProviderKeysPanel />);
    await waitFor(() => expect(fetchCertifiedProviderCredentials).toHaveBeenCalled());
    expect(container.textContent).toBe("");
  });

  it("distinguishes certified process-wide keys from personal model keys", async () => {
    render(<CertifiedProviderKeysPanel />);
    await waitFor(() => expect(screen.getByText("DeepSeek")).toBeTruthy());
    expect(screen.getByText(/process-wide certified routes/i)).toBeTruthy();
    expect(screen.getByText("deepseek · encrypted key stored")).toBeTruthy();
    expect(screen.getByText("anthropic · no certified key")).toBeTruthy();
    expect(screen.getByText("env fallback: on")).toBeTruthy();
    expect(document.body.textContent).not.toContain("sk-");
  });

  it("uses a masked write-only field and clears it after activation", async () => {
    const user = userEvent.setup();
    render(<CertifiedProviderKeysPanel />);
    await waitFor(() => expect(screen.getByText("DeepSeek")).toBeTruthy());
    await user.click(
      screen.getByRole("button", { name: "Replace key for DeepSeek" }),
    );
    const input = screen.getByLabelText("DeepSeek API key") as HTMLInputElement;
    expect(input.type).toBe("password");
    await user.type(input, SECRET);
    await user.click(screen.getByRole("button", { name: "Save and activate" }));
    await waitFor(() =>
      expect(putCertifiedProviderCredential).toHaveBeenCalledWith("deepseek", SECRET),
    );
    expect(screen.queryByLabelText("DeepSeek API key")).toBeNull();
    expect(document.body.textContent).not.toContain(SECRET);
  });

  it("surfaces a value-free failure without rendering the submitted key", async () => {
    vi.mocked(putCertifiedProviderCredential).mockRejectedValue(
      new Error("settings API 503: update unavailable"),
    );
    const user = userEvent.setup();
    render(<CertifiedProviderKeysPanel />);
    await waitFor(() => expect(screen.getByText("DeepSeek")).toBeTruthy());
    await user.click(
      screen.getByRole("button", { name: "Replace key for DeepSeek" }),
    );
    await user.type(screen.getByLabelText("DeepSeek API key"), SECRET);
    await user.click(screen.getByRole("button", { name: "Save and activate" }));
    await waitFor(() => expect(screen.getByRole("alert")).toBeTruthy());
    expect(screen.getByRole("alert").textContent).toContain("update unavailable");
    expect(document.body.textContent).not.toContain(SECRET);
  });
});
