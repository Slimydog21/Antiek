/** Synthetic UNIT microphone/ASR replies exercise the real pane, shared recorder
 * and ASR client. No real microphone, account, provider or live acceptance. */
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { awaitWorkspaceOwnerSession, resumeWorkspaceOwner, setWorkspaceOwner, suspendWorkspaceOwner, workspaceOwnerSession } from "../../lib/accountWorkspaceOwner";
import { useCompanion } from "../companionStore";
import { useTabTrees } from "../tabTreeStore";
import { AgentPane } from "./AgentPane";
import { useAgentPaneStore } from "./agentPaneStore";
import { useAgentThreads } from "./agentThreadStore";
import type { AgentTransport } from "./agentTransport";
import type { AgentPaneTab } from "./agentTypes";

class UnitRecorder {
  static instances: UnitRecorder[] = [];
  state = "inactive";
  mimeType = "audio/webm";
  ondataavailable: ((event: { data: Blob }) => void) | null = null;
  onstop: (() => void) | null = null;
  constructor(readonly stream: MediaStream) { UnitRecorder.instances.push(this); }
  start() { this.state = "recording"; }
  stop() {
    if (this.state === "inactive") return;
    this.state = "inactive";
    this.ondataavailable?.({ data: new Blob(["UNIT audio"], { type: this.mimeType }) });
    this.onstop?.();
  }
}
const tab: AgentPaneTab = { id: "agent:pane:x:voice", agentId: "x:voice", title: "UNIT voice agent", scope: "cross-project" };
const send = vi.fn<AgentTransport["send"]>();
const transport: AgentTransport = { kind: "whole", send };
const stopTrack = vi.fn();
const stream = { getTracks: () => [{ stop: stopTrack }] } as unknown as MediaStream;
const getUserMedia = vi.fn<() => Promise<MediaStream>>();
const fetchAudio = vi.fn<typeof fetch>();
function open() { useCompanion.getState().openAgentTab({ kind: "dialogue", agentId: tab.agentId, title: tab.title, scope: tab.scope }); }
function host() { return render(<MemoryRouter><AgentPane tab={tab} transport={transport} /></MemoryRouter>); }
function draft() { return screen.getByRole<HTMLTextAreaElement>("combobox", { name: "Ask the agent" }); }
function transcript(text = "UNIT spoken thought") { return new Response(JSON.stringify({ transcript: text, language: "en", duration_seconds: 2 }), { status: 200, headers: { "Content-Type": "application/json" } }); }
async function start() {
  fireEvent.click(screen.getByRole("button", { name: "Record voice" }));
  await screen.findByRole("button", { name: "Stop recording" });
}
async function record() { await start(); fireEvent.click(screen.getByRole("button", { name: "Stop recording" })); await screen.findByRole("button", { name: "Use transcript" }); }
beforeEach(async () => {
  Object.defineProperty(window, "matchMedia", { configurable: true, value: (media: string) => ({ media, matches: true, addEventListener() {}, removeEventListener() {} }) });
  setWorkspaceOwner(null); setWorkspaceOwner("unit-voice-A"); await awaitWorkspaceOwnerSession(workspaceOwnerSession());
  useCompanion.getState().reset(); useAgentThreads.getState().reset(); useAgentPaneStore.getState().reset();
  window.sessionStorage.clear(); open();
  UnitRecorder.instances = []; stopTrack.mockReset(); getUserMedia.mockReset().mockResolvedValue(stream); fetchAudio.mockReset().mockResolvedValue(transcript()); send.mockReset().mockResolvedValue({ text: "UNIT agent reply", shape: "SYNTHESIS" });
  vi.stubGlobal("MediaRecorder", UnitRecorder); vi.stubGlobal("fetch", fetchAudio);
  Object.defineProperty(navigator, "mediaDevices", { configurable: true, value: { getUserMedia } });
});
afterEach(() => { cleanup(); setWorkspaceOwner(null); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

describe("real agent voice draft flow", () => {
  it("does nothing on mount; explicit record, stop and review append to the draft without sending", async () => {
    host(); expect(getUserMedia).not.toHaveBeenCalled(); expect(fetchAudio).not.toHaveBeenCalled();
    fireEvent.change(draft(), { target: { value: "UNIT typed idea" } });
    await record();
    expect(getUserMedia).toHaveBeenCalledTimes(1); expect(fetchAudio).toHaveBeenCalledTimes(1);
    expect(fetchAudio.mock.calls[0][0]).toContain("/voice/transcribe"); expect(fetchAudio.mock.calls[0][1]?.method).toBe("POST");
    expect(stopTrack).toHaveBeenCalledTimes(1); expect(draft().value).toBe("UNIT typed idea"); expect(send).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Use transcript" }));
    expect(draft().value).toBe("UNIT typed idea\nUNIT spoken thought"); expect(send).not.toHaveBeenCalled(); expect(document.activeElement).toBe(draft());
    fireEvent.keyDown(draft(), { key: "Enter" }); await waitFor(() => expect(send).toHaveBeenCalledTimes(1));
  });

  it("reviewed words can be corrected, while text typed during transcription is preserved", async () => {
    let resolve!: (response: Response) => void;
    fetchAudio.mockReturnValue(new Promise<Response>((done) => { resolve = done; }));
    host(); await start(); fireEvent.click(screen.getByRole("button", { name: "Stop recording" }));
    await waitFor(() => expect(fetchAudio).toHaveBeenCalledTimes(1));
    fireEvent.change(draft(), { target: { value: "UNIT newest typed text" } });
    await act(async () => resolve(transcript()));
    fireEvent.change(screen.getByRole("textbox", { name: "Voice transcript" }), { target: { value: "UNIT corrected words" } });
    fireEvent.click(screen.getByRole("button", { name: "Use transcript" }));
    expect(draft().value).toBe("UNIT newest typed text\nUNIT corrected words"); expect(send).not.toHaveBeenCalled();
  });

  it("Escape in the actual composer stops the recorder, retains the agent and offers review", async () => {
    host(); await start(); expect(UnitRecorder.instances[0].state).toBe("recording");
    fireEvent.keyDown(draft(), { key: "Escape" });
    await screen.findByRole("button", { name: "Use transcript" });
    expect(UnitRecorder.instances[0].state).toBe("inactive"); expect(stopTrack).toHaveBeenCalledTimes(1);
    expect(useCompanion.getState().tabs.some((entry) => entry.id === tab.id)).toBe(true); expect(send).not.toHaveBeenCalled();
  });

  it.each(["recording", "review"] as const)("discarding during %s never inserts words or sends", async (phase) => {
    host(); fireEvent.change(draft(), { target: { value: "UNIT retained typed words" } });
    if (phase === "recording") await start(); else await record();
    fireEvent.click(screen.getByRole("button", { name: "Discard voice" }));
    expect(draft().value).toBe("UNIT retained typed words"); expect(stopTrack).toHaveBeenCalledTimes(1); expect(send).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Record voice" })).not.toBeNull();
    expect(fetchAudio).toHaveBeenCalledTimes(phase === "recording" ? 0 : 1);
  });

  it("permission denial remains an honest error and typing continues", async () => {
    getUserMedia.mockRejectedValue(new DOMException("UNIT denied", "NotAllowedError"));
    host(); fireEvent.change(draft(), { target: { value: "UNIT typed fallback" } });
    fireEvent.click(screen.getByRole("button", { name: "Record voice" }));
    expect((await screen.findByRole("alert")).textContent).toContain("Microphone permission was denied");
    expect(fetchAudio).not.toHaveBeenCalled(); expect(draft().value).toBe("UNIT typed fallback");
    fireEvent.keyDown(draft(), { key: "Enter" }); await waitFor(() => expect(send).toHaveBeenCalledTimes(1));
  });

  it.each([403, 503])("HTTP %s does not become an empty transcript or success", async (status) => {
    fetchAudio.mockResolvedValue(new Response("UNIT failure", { status }));
    host(); fireEvent.change(draft(), { target: { value: "UNIT retained typed prompt" } });
    await start(); fireEvent.click(screen.getByRole("button", { name: "Stop recording" }));
    const error = await screen.findByRole("alert");
    expect(error.textContent).toContain(status === 403 ? "restricted to operators" : "isn’t available");
    expect(screen.queryByRole("button", { name: "Use transcript" })).toBeNull(); expect(draft().value).toBe("UNIT retained typed prompt"); expect(send).not.toHaveBeenCalled();
  });

  it.each(["", "  ", "...", null, 42])("empty or malformed transcript %s is refused", async (text) => {
    fetchAudio.mockResolvedValue(new Response(JSON.stringify({ transcript: text, language: null, duration_seconds: 1 }), { status: 200 }));
    host(); await start(); fireEvent.click(screen.getByRole("button", { name: "Stop recording" }));
    await screen.findByRole("alert");
    expect(screen.queryByRole("button", { name: "Use transcript" })).toBeNull(); expect(draft().value).toBe(""); expect(send).not.toHaveBeenCalled();
  });

  it("retired pending microphone permission stops its late stream without recording or uploading", async () => {
    let resolve!: (value: MediaStream) => void;
    getUserMedia.mockReturnValue(new Promise<MediaStream>((done) => { resolve = done; }));
    host(); fireEvent.click(screen.getByRole("button", { name: "Record voice" }));
    expect(getUserMedia).toHaveBeenCalledTimes(1);
    act(() => { setWorkspaceOwner("unit-voice-B"); setWorkspaceOwner("unit-voice-A"); });
    await act(async () => resolve(stream));
    expect(stopTrack).toHaveBeenCalledTimes(1); expect(UnitRecorder.instances).toHaveLength(0); expect(fetchAudio).not.toHaveBeenCalled();
    expect(screen.queryByRole("combobox", { name: "Ask the agent" })).toBeNull();
  });

  it.each(["owner", "incarnation", "project"] as const)("retiring %s during ASR aborts and refuses the late text", async (kind) => {
    let resolve!: (value: Response) => void;
    fetchAudio.mockReturnValue(new Promise<Response>((done) => { resolve = done; }));
    host(); await start(); fireEvent.click(screen.getByRole("button", { name: "Stop recording" }));
    await waitFor(() => expect(fetchAudio).toHaveBeenCalledTimes(1));
    const signal = fetchAudio.mock.calls[0][1]?.signal;
    act(() => {
      if (kind === "owner") { setWorkspaceOwner("unit-voice-B"); setWorkspaceOwner("unit-voice-A"); }
      else if (kind === "incarnation") { useCompanion.getState().closeAgentTab(tab.id); open(); }
      else useTabTrees.setState((state) => ({ contextEpoch: state.contextEpoch + 1 }));
    });
    expect(signal?.aborted).toBe(true);
    await act(async () => resolve(transcript("UNIT retired transcript")));
    expect(document.body.textContent).not.toContain("UNIT retired transcript"); expect(screen.queryByRole("button", { name: "Use transcript" })).toBeNull(); expect(send).not.toHaveBeenCalled();
  });

  it("same-owner suspension stops capture, preserves the draft and requires a fresh explicit start", async () => {
    host(); fireEvent.change(draft(), { target: { value: "UNIT same-owner draft" } }); await start();
    act(() => suspendWorkspaceOwner());
    expect(UnitRecorder.instances[0].state).toBe("inactive"); expect(stopTrack).toHaveBeenCalledTimes(1); expect(fetchAudio).not.toHaveBeenCalled(); expect(draft().value).toBe("UNIT same-owner draft");
    expect(useAgentPaneStore.getState().recording[tab.id]).toBe(false);
    await act(async () => { resumeWorkspaceOwner(); await awaitWorkspaceOwnerSession(workspaceOwnerSession()); });
    expect(getUserMedia).toHaveBeenCalledTimes(1); expect(fetchAudio).not.toHaveBeenCalled();
    expect(useAgentPaneStore.getState().recording[tab.id]).toBe(false);
    await record(); fireEvent.click(screen.getByRole("button", { name: "Use transcript" }));
    expect(draft().value).toBe("UNIT same-owner draft\nUNIT spoken thought"); expect(send).not.toHaveBeenCalled();
  });

  it("descriptor title clones retain the admitted attempt and transcript", async () => {
    host(); await start();
    act(() => useCompanion.setState((state) => ({ tabs: state.tabs.map((entry) => ({ ...entry, title: "UNIT cloned title" })) })));
    fireEvent.click(screen.getByRole("button", { name: "Stop recording" }));
    await screen.findByRole("button", { name: "Use transcript" }); fireEvent.click(screen.getByRole("button", { name: "Use transcript" }));
    expect(draft().value).toBe("UNIT spoken thought"); expect(getUserMedia).toHaveBeenCalledTimes(1);
  });

  it("an unmounted attempt stops its track and cannot upload", async () => {
    const view = host(); await start(); view.unmount();
    expect(stopTrack).toHaveBeenCalledTimes(1); expect(fetchAudio).not.toHaveBeenCalled(); expect(send).not.toHaveBeenCalled();
  });
});
