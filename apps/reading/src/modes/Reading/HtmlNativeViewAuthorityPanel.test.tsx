import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import HtmlNativeViewAuthorityPanel from "./HtmlNativeViewAuthorityPanel";

afterEach(() => {
  cleanup();
});

describe("HtmlNativeViewAuthorityPanel", () => {
  it("authorizes when sha provided", async () => {
    render(
      <HtmlNativeViewAuthorityPanel initialAssetId="book-1" />,
    );
    fireEvent.change(screen.getByTestId("hnva-sha"), {
      target: { value: "sha256:ready" },
    });
    fireEvent.click(screen.getByTestId("hnva-run"));
    await waitFor(() => {
      expect(screen.getByTestId("hnva-human").textContent).toMatch(/true/);
      expect(screen.getByTestId("hnva-primary").textContent).toMatch(/html/);
    });
  });

  it("does not invent ready without sha", async () => {
    render(
      <HtmlNativeViewAuthorityPanel initialAssetId="book-1" />,
    );
    fireEvent.click(screen.getByTestId("hnva-run"));
    await waitFor(() => {
      expect(screen.getByTestId("hnva-human").textContent).toMatch(/false/);
      expect(screen.getByTestId("hnva-primary").textContent).toMatch(
        /unavailable/,
      );
    });
  });
});
