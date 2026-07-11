import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import HtmlPreferencePanel from "./HtmlPreferencePanel";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("HtmlPreferencePanel", () => {
  it("decides via injectable and shows HTML preferred", async () => {
    const decideFn = vi.fn(async () => ({
      mode: "html" as const,
      preferred: true,
      reason: "html_ready",
      notes: ["HTML projection ready"],
    }));
    render(<HtmlPreferencePanel decideFn={decideFn} />);
    fireEvent.click(screen.getByTestId("html-preference-decide"));
    await waitFor(() => {
      expect(screen.getByTestId("html-preference-result")).toBeTruthy();
    });
    expect(decideFn).toHaveBeenCalledWith({
      html_ready: true,
      pdf_available: true,
      require_html: true,
    });
    expect(screen.getByTestId("html-preference-mode").textContent).toMatch(/HTML/i);
    expect(screen.getByTestId("html-preference-preferred").textContent).toMatch(/yes/i);
  });

  it("shows metadata_only when PDF blocked by policy", async () => {
    const decideFn = vi.fn(async () => ({
      mode: "metadata_only" as const,
      preferred: false,
      reason: "pdf_blocked_by_html_policy",
      notes: [],
    }));
    render(
      <HtmlPreferencePanel
        decideFn={decideFn}
        initialHtmlReady={false}
        initialPdfAvailable={true}
        initialRequireHtml={true}
      />,
    );
    fireEvent.click(screen.getByTestId("html-preference-decide"));
    await waitFor(() => {
      expect(screen.getByTestId("html-preference-mode").textContent).toMatch(
        /metadata/i,
      );
    });
    expect(screen.getByTestId("html-preference-preferred").textContent).toMatch(/no/i);
  });

  it("surfaces decide errors", async () => {
    const decideFn = vi.fn(async () => {
      throw new Error("decide failed");
    });
    render(<HtmlPreferencePanel decideFn={decideFn} />);
    fireEvent.click(screen.getByTestId("html-preference-decide"));
    await waitFor(() => {
      expect(screen.getByTestId("html-preference-error").textContent).toMatch(
        /decide failed/,
      );
    });
    expect(screen.queryByTestId("html-preference-result")).toBeNull();
  });
});
