import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import AIActionFailure from "./AIActionFailure";
import { FAILURE_HEADLINES } from "../lib/api";

describe("AIActionFailure coded failures", () => {
  it("renders verbatim headline per code", () => {
    const codes = [
      "backend_unreachable",
      "provider_unconfigured",
      "provider_upstream_error",
      "timeout",
      "unknown",
    ] as const;
    for (const code of codes) {
      const { unmount } = render(
        <AIActionFailure
          title="Title"
          code={code}
          onRetry={vi.fn()}
        />,
      );
      expect(screen.getByText(new RegExp(FAILURE_HEADLINES[code].slice(0, 20)))).toBeTruthy();
      unmount();
    }
  });

  it("hides retry when provider_unconfigured", () => {
    render(
      <AIActionFailure
        title="Title"
        code="provider_unconfigured"
        retryable={false}
        onRetry={vi.fn()}
      />,
    );
    expect(screen.queryByRole("button", { name: "Try again" })).toBeNull();
  });

  it("legacy no-code no-reason branch unchanged", () => {
    render(<AIActionFailure title="T" onRetry={vi.fn()} />);
    expect(screen.getByText(/model provider isn’t configured/i)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Try again" })).toBeTruthy();
  });

  it("legacy no-code reason branch unchanged", () => {
    render(
      <AIActionFailure title="T" reason="quota exceeded" onRetry={vi.fn()} />,
    );
    expect(screen.getByText(/engine reported a problem/i)).toBeTruthy();
    expect(screen.getByText(/Engine: quota exceeded/)).toBeTruthy();
  });
});