/**
 * The "I wrote this" option is gated on the API's capability route (FFX
 * SPR-02, A-06 client half; backend INBOX 2026-09-27T00:40Z). It is enabled
 * ONLY when GET /sources/upload/attestations lists `user_authored_private`,
 * and then that exact token is sent. A 404, an error, or a capability without
 * the token keeps it disabled with an honest "needs a server update" state and
 * a Retry; the client never falls back to the legacy public class.
 *
 * Mocked at the network boundary (apiFetch) so the real upload client runs.
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }));

vi.mock("../../lib/api", async (orig) => {
  const actual = await orig<typeof import("../../lib/api")>();
  return { ...actual, apiFetch: (...args: unknown[]) => apiFetchMock(...args) };
});

import Sources from "./index";
import * as uploadApi from "../../lib/sourceUploadApi";

const LEGACY_PUBLIC_TOKEN = ["user", "owned"].join("_");
const SERVER_UPDATE_COPY = "This needs a server update. Try again later.";
const AUTHORED_LABEL = /I wrote this/;

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
const ticket = () =>
  json({ document_id: "doc-upload-1", detected_kind: "md", reader_html_available: true, chunk_count: 0 }, 201);

type CapabilityAnswer = () => Promise<Response>;

function routeFetch(capability: CapabilityAnswer) {
  apiFetchMock.mockImplementation((url: unknown) => {
    const u = String(url);
    if (u.endsWith("/sources/upload/attestations")) return capability();
    if (u.endsWith("/sources/upload")) return Promise.resolve(ticket());
    return Promise.resolve(json({}));
  });
}

function renderWithFile() {
  render(
    <MemoryRouter initialEntries={["/sources"]}>
      <Sources />
    </MemoryRouter>,
  );
  const input = document.querySelector('input[type="file"]') as HTMLInputElement;
  fireEvent.change(input, { target: { files: [new File(["# Draft"], "draft.md", { type: "text/markdown" })] } });
}

const authoredRadio = () => screen.getByLabelText(AUTHORED_LABEL) as HTMLInputElement;

function uploadForms(): FormData[] {
  return apiFetchMock.mock.calls
    .filter(([url]) => String(url).endsWith("/sources/upload"))
    .map(([, init]) => (init as RequestInit).body as FormData);
}

describe("Sources authored upload is capability-gated", () => {
  beforeEach(() => {
    apiFetchMock.mockReset();
    // Optional call so this file shows behavioural reds on a head without it.
    (uploadApi as { resetUploadAttestationsCache?: () => void }).resetUploadAttestationsCache?.();
  });
  afterEach(cleanup);

  it.each([
    ["404 (an older API)", () => Promise.resolve(new Response("Not Found", { status: 404 }))],
    ["a network error", () => Promise.reject(new TypeError("Failed to fetch"))],
    ["a 500", () => Promise.resolve(new Response("boom", { status: 500 }))],
  ])("keeps the authored option disabled on %s, with the server-update copy", async (_name, answer) => {
    routeFetch(answer as CapabilityAnswer);
    renderWithFile();
    expect(await screen.findByText(SERVER_UPDATE_COPY)).toBeTruthy();
    expect(authoredRadio().disabled).toBe(true);
    // Personal reading is still available and selected.
    expect((screen.getByLabelText(/Personal reading/) as HTMLInputElement).checked).toBe(true);
  });

  it("keeps it disabled when the capability does not list user_authored_private", async () => {
    routeFetch(() =>
      Promise.resolve(json({ accepted: ["personal_reading", LEGACY_PUBLIC_TOKEN], authored_default: LEGACY_PUBLIC_TOKEN, aliases: {} })),
    );
    renderWithFile();
    expect(await screen.findByText(SERVER_UPDATE_COPY)).toBeTruthy();
    expect(authoredRadio().disabled).toBe(true);
  });

  it("Retry refetches the capability and enables the option once the API lists the token", async () => {
    let calls = 0;
    routeFetch(() => {
      calls += 1;
      return calls === 1
        ? Promise.resolve(new Response("Not Found", { status: 404 }))
        : Promise.resolve(json({ accepted: ["personal_reading", "user_authored_private"], authored_default: "user_authored_private", aliases: {} }));
    });
    renderWithFile();
    expect(await screen.findByText(SERVER_UPDATE_COPY)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(authoredRadio().disabled).toBe(false));
    expect(screen.queryByText(SERVER_UPDATE_COPY)).toBeNull();
    expect(calls).toBe(2);
  });

  it("enables it when the token is listed and sends exactly user_authored_private", async () => {
    routeFetch(() =>
      Promise.resolve(json({ accepted: ["personal_reading", "user_authored_private", LEGACY_PUBLIC_TOKEN], authored_default: "user_authored_private", aliases: { [LEGACY_PUBLIC_TOKEN]: "user_authored_private" } })),
    );
    renderWithFile();
    await waitFor(() => expect(authoredRadio().disabled).toBe(false));
    // The label states the privacy property the user is consenting to.
    expect(screen.getByText("I wrote this (notes or drafts). Only you can read it. It opens in the reader with full text, highlights and research.")).toBeTruthy();
    expect(screen.getByText(/Personal reading — .*Only you can read it\./)).toBeTruthy();
    fireEvent.click(authoredRadio());
    fireEvent.click(screen.getByLabelText(/I confirm the attestation above/));
    fireEvent.click(screen.getByRole("button", { name: "Upload and convert" }));
    await waitFor(() => expect(uploadForms()).toHaveLength(1));
    const form = uploadForms()[0];
    expect(form.get("acquisition_attestation")).toBe("user_authored_private");
    expect(form.get("acquisition_attestation")).not.toBe(LEGACY_PUBLIC_TOKEN);
  });

  it("leaves the personal_reading upload unchanged when the capability route is absent", async () => {
    routeFetch(() => Promise.resolve(new Response("Not Found", { status: 404 })));
    renderWithFile();
    await screen.findByText(SERVER_UPDATE_COPY);
    fireEvent.click(screen.getByLabelText(/I confirm the attestation above/));
    fireEvent.click(screen.getByRole("button", { name: "Upload and convert" }));
    await waitFor(() => expect(uploadForms()).toHaveLength(1));
    const form = uploadForms()[0];
    expect(form.get("acquisition_attestation")).toBe("personal_reading");
    expect(form.has("title")).toBe(false);
    expect(await screen.findByRole("button", { name: "Open in reader" })).toBeTruthy();
  });
});
