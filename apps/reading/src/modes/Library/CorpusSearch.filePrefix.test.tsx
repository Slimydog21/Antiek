import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import CorpusSearch from "./CorpusSearch";

const { searchMock } = vi.hoisted(() => ({ searchMock: vi.fn() }));
vi.mock("../../api/corpusSearch", () => ({ corpusSearch: searchMock }));

beforeEach(() => {
  searchMock.mockReset();
  searchMock.mockRejectedValue(new Error("Search is temporarily unavailable."));
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

function drop(file: File) {
  render(<CorpusSearch onOpen={vi.fn()} />);
  fireEvent.drop(screen.getByTestId("corpus-search"), { dataTransfer: { files: [file] } });
}

describe("Dropped-file query reads (synthetic input; search rejects)", () => {
  it.each([
    ["ASCII", "a useful query ".repeat(10000)],
    ["UTF8 and BOM", "\uFEFF" + "é漢🙂".repeat(10000)],
  ])("bounds an oversized %s file before decoding while preserving its query prefix", async (_label, contents) => {
    const file = new File([contents], "query.txt", { type: "text/plain" });
    const wholeRead = vi.spyOn(file, "text").mockRejectedValue(new Error("Unbounded whole-file read"));
    const nativeSlice = file.slice.bind(file);
    const readSizes: number[] = [];
    const slice = vi.spyOn(file, "slice").mockImplementation((start, end, type) => {
      const prefix = nativeSlice(start, end, type);
      readSizes.push(prefix.size);
      return prefix;
    });
    drop(file);
    await waitFor(() => expect(searchMock).toHaveBeenCalledOnce());
    expect(wholeRead).not.toHaveBeenCalled();
    expect(slice).toHaveBeenCalledWith(0, 8192);
    expect(readSizes).toEqual([8192]);
    expect(searchMock.mock.calls).toEqual([[contents.replace(/^\uFEFF/, "").slice(0, 2000).trim()]]);
    expect((await screen.findByRole("alert")).textContent).toContain("temporarily unavailable");
    expect(screen.queryByText(/Nothing in your corpus matched/)).toBeNull();
  });

  it.each([40, 8192])("keeps the existing text path within the %i-byte read bound", async (size) => {
    const contents = "x".repeat(size);
    const file = new File([contents], "small-query.txt");
    const read = vi.spyOn(file, "text");
    const slice = vi.spyOn(file, "slice");
    drop(file);
    await waitFor(() => expect(searchMock).toHaveBeenCalledOnce());
    expect(read).toHaveBeenCalledOnce();
    expect(slice).not.toHaveBeenCalled();
    expect(searchMock.mock.calls).toEqual([[contents.slice(0, 2000)]]);
    await screen.findByRole("alert");
  });
});
