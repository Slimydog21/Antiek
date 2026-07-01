import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { TocItem } from "../../api/books";
import TocPanel from "./TocPanel";

afterEach(cleanup);

const toc = (over: Partial<TocItem>): TocItem => ({
  title: "Chapter",
  page_index: 0,
  level: 0,
  ...over,
});

describe("TocPanel", () => {
  it("jumps only for safe non-negative integer page indexes", () => {
    const onJump = vi.fn();
    render(
      <TocPanel
        currentPageIndex={0}
        onJump={onJump}
        toc={[
          toc({ title: "Valid page", page_index: 2 }),
          toc({ title: "Unresolved page", page_index: null }),
          toc({ title: "Fractional page", page_index: 2.5 }),
          toc({ title: "Negative page", page_index: -1 }),
          toc({ title: "Unsafe page", page_index: Number.MAX_SAFE_INTEGER + 1 }),
        ]}
      />,
    );

    const nav = screen.getByRole("navigation", { name: "Table of contents" });
    fireEvent.click(within(nav).getByRole("button", { name: "Valid page" }));
    expect(onJump).toHaveBeenCalledWith(2);

    for (const name of ["Unresolved page", "Fractional page", "Negative page", "Unsafe page"]) {
      const button = within(nav).getByRole("button", { name }) as HTMLButtonElement;
      expect(button.disabled).toBe(true);
      fireEvent.click(button);
    }
    expect(onJump).toHaveBeenCalledTimes(1);
  });
});
