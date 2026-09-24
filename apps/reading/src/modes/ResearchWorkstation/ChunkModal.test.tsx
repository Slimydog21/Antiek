import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { StrictMode } from "react";

import type { ChunkResponse } from "../../lib/api";
import { getChunk } from "../../lib/api";
import ChunkModal from "./ChunkModal";

vi.mock("../../lib/api", () => ({ getChunk: vi.fn() }));

const getChunkMock = vi.mocked(getChunk);

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

function chunk(over: Partial<ChunkResponse> = {}): ChunkResponse {
  return {
    chunk_id: "chunk-1",
    text: "Readable evidence",
    section_path: "Page 12",
    token_count: 24,
    document_id: "doc-1",
    document_title: "On Growth and Form",
    source_tier: 1,
    servable: true,
    servability: null,
    ...over,
  };
}

afterEach(() => {
  cleanup();
  getChunkMock.mockReset();
});

describe("ChunkModal Werner evidence boundary", () => {
  it("notifies once only after current readable evidence is committed", async () => {
    const pending = deferred<ChunkResponse>();
    getChunkMock.mockReturnValue(pending.promise);
    const onEvidenceOpened = vi.fn();
    render(
      <ChunkModal
        chunkId="chunk-1"
        onClose={vi.fn()}
        onEvidenceOpened={onEvidenceOpened}
      />,
    );

    expect(onEvidenceOpened).not.toHaveBeenCalled();
    pending.resolve(chunk());
    await waitFor(() =>
      expect(screen.getByText("Readable evidence")).toBeTruthy(),
    );
    expect(onEvidenceOpened).toHaveBeenCalledTimes(1);
  });

  it("stays silent for withheld evidence and fetch failure", async () => {
    const onEvidenceOpened = vi.fn();
    getChunkMock.mockResolvedValueOnce(
      chunk({ text: "", servable: false, servability: "restricted" }),
    );
    const view = render(
      <ChunkModal
        chunkId="restricted"
        onClose={vi.fn()}
        onEvidenceOpened={onEvidenceOpened}
      />,
    );
    await waitFor(() =>
      expect(screen.getByText(/isn’t available/)).toBeTruthy(),
    );
    expect(onEvidenceOpened).not.toHaveBeenCalled();

    getChunkMock.mockRejectedValueOnce(new Error("offline"));
    view.rerender(
      <ChunkModal
        chunkId="failed"
        onClose={vi.fn()}
        onEvidenceOpened={onEvidenceOpened}
      />,
    );
    await waitFor(() => expect(screen.getByText("offline")).toBeTruthy());
    expect(onEvidenceOpened).not.toHaveBeenCalled();
  });

  it("ignores a superseded response and notifies for the current source", async () => {
    const old = deferred<ChunkResponse>();
    const current = deferred<ChunkResponse>();
    getChunkMock
      .mockReturnValueOnce(old.promise)
      .mockReturnValueOnce(current.promise);
    const onEvidenceOpened = vi.fn();
    const view = render(
      <ChunkModal
        chunkId="old"
        onClose={vi.fn()}
        onEvidenceOpened={onEvidenceOpened}
      />,
    );

    view.rerender(
      <ChunkModal
        chunkId="current"
        onClose={vi.fn()}
        onEvidenceOpened={onEvidenceOpened}
      />,
    );
    old.resolve(chunk({ chunk_id: "old", text: "Stale evidence" }));
    current.resolve(chunk({ chunk_id: "current", text: "Current evidence" }));
    await waitFor(() =>
      expect(screen.getByText("Current evidence")).toBeTruthy(),
    );

    expect(screen.queryByText("Stale evidence")).toBeNull();
    expect(onEvidenceOpened).toHaveBeenCalledTimes(1);
  });

  it("a throwing observer cannot corrupt readable evidence", async () => {
    getChunkMock.mockResolvedValue(chunk());
    const observer = vi.fn(() => {
      throw new Error("animation unavailable");
    });
    render(
      <ChunkModal
        chunkId="chunk-1"
        onClose={vi.fn()}
        onEvidenceOpened={observer}
      />,
    );

    await waitFor(() =>
      expect(screen.getByText("Readable evidence")).toBeTruthy(),
    );
    expect(observer).toHaveBeenCalledTimes(1);
  });

  it("notifies once under StrictMode effect replay", async () => {
    getChunkMock.mockResolvedValue(chunk());
    const onEvidenceOpened = vi.fn();
    render(
      <StrictMode>
        <ChunkModal
          chunkId="chunk-1"
          onClose={vi.fn()}
          onEvidenceOpened={onEvidenceOpened}
        />
      </StrictMode>,
    );

    await waitFor(() =>
      expect(screen.getByText("Readable evidence")).toBeTruthy(),
    );
    expect(onEvidenceOpened).toHaveBeenCalledTimes(1);
  });

  it("treats a deliberate close and reopen as a fresh evidence opening", async () => {
    getChunkMock.mockResolvedValue(chunk());
    const onEvidenceOpened = vi.fn();
    const view = render(
      <ChunkModal
        chunkId="chunk-1"
        onClose={vi.fn()}
        onEvidenceOpened={onEvidenceOpened}
      />,
    );
    await waitFor(() => expect(onEvidenceOpened).toHaveBeenCalledTimes(1));

    view.rerender(
      <ChunkModal
        chunkId={null}
        onClose={vi.fn()}
        onEvidenceOpened={onEvidenceOpened}
      />,
    );
    await waitFor(() =>
      expect(screen.queryByText("Readable evidence")).toBeNull(),
    );
    view.rerender(
      <ChunkModal
        chunkId="chunk-1"
        onClose={vi.fn()}
        onEvidenceOpened={onEvidenceOpened}
      />,
    );

    await waitFor(() => expect(onEvidenceOpened).toHaveBeenCalledTimes(2));
    expect(getChunkMock).toHaveBeenCalledTimes(2);
  });

  it("close and unmount before resolution remain silent", async () => {
    const pending = deferred<ChunkResponse>();
    getChunkMock.mockReturnValue(pending.promise);
    const onEvidenceOpened = vi.fn();
    const view = render(
      <ChunkModal
        chunkId="chunk-1"
        onClose={vi.fn()}
        onEvidenceOpened={onEvidenceOpened}
      />,
    );

    view.rerender(
      <ChunkModal
        chunkId={null}
        onClose={vi.fn()}
        onEvidenceOpened={onEvidenceOpened}
      />,
    );
    view.unmount();
    await act(async () => pending.resolve(chunk()));
    expect(onEvidenceOpened).not.toHaveBeenCalled();
  });
});
