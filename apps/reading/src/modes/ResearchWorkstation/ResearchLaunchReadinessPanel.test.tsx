import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import ResearchLaunchReadinessPanel from "./ResearchLaunchReadinessPanel";

afterEach(() => {
  cleanup();
});

describe("ResearchLaunchReadinessPanel", () => {
  it("shows launch ready with live false", async () => {
    render(
      <ResearchLaunchReadinessPanel initialSessionId="sess-1" />,
    );
    fireEvent.click(screen.getByTestId("rlr-run"));
    await waitFor(() => {
      expect(screen.getByTestId("rlr-live").textContent).toMatch(/false/);
      expect(screen.getByTestId("rlr-launch").textContent).toMatch(/true/);
    });
  });

  it("null would_exceed without override is not ready", async () => {
    render(
      <ResearchLaunchReadinessPanel initialSessionId="sess-1" />,
    );
    fireEvent.change(screen.getByTestId("rlr-exceed"), {
      target: { value: "null" },
    });
    fireEvent.click(screen.getByTestId("rlr-run"));
    await waitFor(() => {
      expect(screen.getByTestId("rlr-launch").textContent).toMatch(/false/);
      expect(screen.getByTestId("rlr-live").textContent).toMatch(/false/);
    });
  });

  it("surfaces empty session error", async () => {
    render(<ResearchLaunchReadinessPanel initialSessionId="" />);
    fireEvent.click(screen.getByTestId("rlr-run"));
    await waitFor(() => {
      expect(screen.getByTestId("rlr-error").textContent).toMatch(/session_id/);
    });
  });
});
