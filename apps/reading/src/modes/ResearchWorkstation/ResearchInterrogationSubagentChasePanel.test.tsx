import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import ResearchInterrogationSubagentChasePanel from "./ResearchInterrogationSubagentChasePanel";

afterEach(() => {
  cleanup();
});

describe("ResearchInterrogationSubagentChasePanel", () => {
  it("swarm fanout chase ready without dispatch", async () => {
    render(<ResearchInterrogationSubagentChasePanel />);
    fireEvent.click(screen.getByTestId("risc-compose"));
    await waitFor(() => {
      expect(screen.getByTestId("risc-ready").textContent).toMatch(/true/);
      expect(screen.getByTestId("risc-slots").textContent).toMatch(/2/);
      expect(screen.getByTestId("risc-live").textContent).toMatch(/false/);
      expect(screen.getByTestId("risc-pack").textContent).toMatch(/false/);
      expect(screen.getByTestId("risc-record").textContent).toMatch(/false/);
      expect(screen.getByTestId("risc-prompts").textContent).toMatch(/false/);
    });
  });

  it("no ack not ready", async () => {
    render(<ResearchInterrogationSubagentChasePanel />);
    fireEvent.click(screen.getByTestId("risc-ack"));
    fireEvent.click(screen.getByTestId("risc-compose"));
    await waitFor(() => {
      expect(screen.getByTestId("risc-ready").textContent).toMatch(/false/);
      expect(screen.getByTestId("risc-live").textContent).toMatch(/false/);
    });
  });

  it("would_exceed true blocks readiness", async () => {
    render(<ResearchInterrogationSubagentChasePanel />);
    fireEvent.change(screen.getByTestId("risc-would-exceed"), {
      target: { value: "true" },
    });
    fireEvent.click(screen.getByTestId("risc-compose"));
    await waitFor(() => {
      expect(screen.getByTestId("risc-ready").textContent).toMatch(/false/);
      expect(screen.getByTestId("risc-live").textContent).toMatch(/false/);
    });
  });
});
