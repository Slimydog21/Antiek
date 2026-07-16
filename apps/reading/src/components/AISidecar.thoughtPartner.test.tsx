import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../lib/api", () => ({ apiFetch: vi.fn() }));
vi.mock("../brand/werner/animated", () => ({ WernerThinking: () => null }));
vi.mock("../hooks/useReplyMode", () => ({
  useReplyMode: () => ({ mode: "text", setMode: vi.fn() }),
}));
vi.mock("../werner", () => ({ notifyThoughtPartnerReplyReceived: vi.fn() }));
vi.mock("./SpokenReply", () => ({ default: () => null }));
vi.mock("./ai/ContextPicker", () => ({ default: () => null }));
vi.mock("./ai/aiActions", () => ({
  dispatchAiAction: vi.fn(() => ({ at: 1, label: "opened" })),
  parseAssistantReply: vi.fn(),
  workspaceContextPrompt: () => "WORKSPACE-CONTEXT",
}));

import { apiFetch } from "../lib/api";
import { notifyThoughtPartnerReplyReceived } from "../werner";
import AISidecar from "./AISidecar";
import { dispatchAiAction, parseAssistantReply } from "./ai/aiActions";

const apiFetchMock = vi.mocked(apiFetch);
const notifyReply = vi.mocked(notifyThoughtPartnerReplyReceived);
const dispatchAction = vi.mocked(dispatchAiAction);
const parseReply = vi.mocked(parseAssistantReply);

function response(data: unknown, ok = true, status = 200): Response {
  return { ok, status, json: vi.fn().mockResolvedValue(data) } as unknown as Response;
}

function routeThoughtPartner(result: Response | Promise<Response>): void {
  apiFetchMock.mockImplementation((input: RequestInfo | URL) =>
    input === "/thought-partner"
      ? Promise.resolve(result)
      : Promise.resolve(response({}, false, 404)),
  );
}

function send(prompt = "question one"): void {
  fireEvent.change(screen.getByPlaceholderText("What's the question?"), {
    target: { value: prompt },
  });
  fireEvent.click(screen.getByText("Send"));
}

describe("AISidecar thought-partner Werner edge", () => {
  beforeEach(() => {
    apiFetchMock.mockReset();
    notifyReply.mockReset();
    dispatchAction.mockReset().mockImplementation((action) => ({
      action,
      at: 1,
      label: "noted",
      undo: null,
    }));
    parseReply.mockReset().mockReturnValue({
      prose: "A useful reply",
      actions: [],
      parseErrors: [],
    });
  });
  afterEach(cleanup);

  it("announces a parsed 2xx reply before dispatching its structured action", async () => {
    parseReply.mockReturnValue({
      prose: "A useful reply",
      actions: [{ kind: "toast", level: "ok", message: "ready" }],
      parseErrors: [],
    });
    routeThoughtPartner(response({ text: "reply with action", shape: "SYNTHESIS" }));
    render(<AISidecar />);
    send();

    await waitFor(() => expect(dispatchAction).toHaveBeenCalledOnce());

    expect(notifyReply).toHaveBeenCalledOnce();
    expect(notifyReply.mock.invocationCallOrder[0]).toBeLessThan(
      dispatchAction.mock.invocationCallOrder[0],
    );
    expect(screen.getByText("A useful reply")).toBeTruthy();
  });

  it("stays silent for a non-2xx local CHALLENGE reply", async () => {
    routeThoughtPartner(response({}, false, 503));
    render(<AISidecar />);
    send();

    await waitFor(() => expect(screen.getByText(/unavailable \(HTTP 503\)/)).toBeTruthy());
    expect(notifyReply).not.toHaveBeenCalled();
  });

  it("stays silent when response JSON cannot be decoded", async () => {
    const broken = response({});
    vi.mocked(broken.json).mockRejectedValue(new Error("invalid json"));
    routeThoughtPartner(broken);
    render(<AISidecar />);
    send();

    await waitFor(() => expect(screen.getByText("invalid json")).toBeTruthy());
    expect(notifyReply).not.toHaveBeenCalled();
  });

  it("stays silent when the thought-partner request rejects", async () => {
    routeThoughtPartner(Promise.reject(new Error("network unavailable")));
    render(<AISidecar />);
    send();

    await waitFor(() => expect(screen.getByText("network unavailable")).toBeTruthy());
    expect(notifyReply).not.toHaveBeenCalled();
  });

  it("still announces visible prose when only structured actions have parse warnings", async () => {
    parseReply.mockReturnValue({
      prose: "Visible despite action warning",
      actions: [],
      parseErrors: ["bad action"],
    });
    routeThoughtPartner(response({ text: "reply" }));
    render(<AISidecar />);
    send();

    await waitFor(() => expect(screen.getByText("Visible despite action warning")).toBeTruthy());
    expect(notifyReply).toHaveBeenCalledOnce();
  });

  it("does not announce or dispatch a reply that arrives after unmount", async () => {
    let resolve!: (value: Response) => void;
    routeThoughtPartner(new Promise<Response>((done) => { resolve = done; }));
    const view = render(<AISidecar />);
    send();
    view.unmount();

    await act(async () => { resolve(response({ text: "late reply" })); });

    expect(notifyReply).not.toHaveBeenCalled();
    expect(dispatchAction).not.toHaveBeenCalled();
  });

  it("attributes response actions to the prompt snapshot, not a later edit", async () => {
    let resolve!: (value: Response) => void;
    routeThoughtPartner(new Promise<Response>((done) => { resolve = done; }));
    parseReply.mockReturnValue({
      prose: "reply",
      actions: [{ kind: "toast", level: "ok", message: "ready" }],
      parseErrors: [],
    });
    render(<AISidecar />);
    send("original question");
    fireEvent.change(screen.getByPlaceholderText("What's the question?"), {
      target: { value: "edited while pending" },
    });

    await act(async () => { resolve(response({ text: "reply" })); });
    await waitFor(() => expect(dispatchAction).toHaveBeenCalledOnce());

    expect(dispatchAction.mock.calls[0][1]).toMatchObject({
      operator_prompt: "original question",
      investigation_id: "__sidecar__",
    });
  });

  it("keeps the visible reply and later actions when one action dispatch fails", async () => {
    parseReply.mockReturnValue({
      prose: "Reply survives action trouble",
      actions: [
        { kind: "toast", level: "warn", message: "first" },
        { kind: "toast", level: "ok", message: "second" },
      ],
      parseErrors: [],
    });
    dispatchAction
      .mockImplementationOnce(() => { throw new Error("toast unavailable"); })
      .mockImplementationOnce((action) => ({ action, at: 2, label: "second", undo: null }));
    routeThoughtPartner(response({ text: "reply" }));
    render(<AISidecar />);
    send();

    await waitFor(() => expect(screen.getByText("Reply survives action trouble")).toBeTruthy());
    expect(notifyReply).toHaveBeenCalledOnce();
    expect(dispatchAction).toHaveBeenCalledTimes(2);
    expect(screen.getByText("second")).toBeTruthy();
  });

  it("refuses a reply action that would close its own transparency surface", async () => {
    parseReply.mockReturnValue({
      prose: "Keep this reply inspectable",
      actions: [
        { kind: "close_panel", id: "shortcuts:aisidecar" },
        { kind: "toast", level: "ok", message: "still here" },
      ],
      parseErrors: [],
    });
    routeThoughtPartner(response({ text: "reply" }));
    render(<AISidecar />);
    send();

    await waitFor(() => expect(screen.getByText("Keep this reply inspectable")).toBeTruthy());
    expect(notifyReply).toHaveBeenCalledOnce();
    expect(dispatchAction).toHaveBeenCalledOnce();
    expect(dispatchAction.mock.calls[0][0]).toMatchObject({
      kind: "toast",
      message: "still here",
    });
  });
});
