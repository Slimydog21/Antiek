import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import FloatingInstanceTrayPanel from "./FloatingInstanceTrayPanel";

afterEach(() => {
  cleanup();
});

describe("FloatingInstanceTrayPanel", () => {
  it("collective tray ready without dispatch", async () => {
    render(<FloatingInstanceTrayPanel />);
    fireEvent.click(screen.getByTestId("fit-compose"));
    await waitFor(() => {
      expect(screen.getByTestId("fit-ready").textContent).toMatch(/true/);
      expect(screen.getByTestId("fit-pack").textContent).toMatch(/false/);
      expect(screen.getByTestId("fit-merged").textContent).toMatch(/false/);
      expect(screen.getByTestId("fit-live").textContent).toMatch(/false/);
    });
  });

  it("no ack blocks collective", async () => {
    render(<FloatingInstanceTrayPanel />);
    fireEvent.click(screen.getByTestId("fit-ack"));
    fireEvent.click(screen.getByTestId("fit-compose"));
    await waitFor(() => {
      expect(screen.getByTestId("fit-ready").textContent).toMatch(/false/);
      expect(screen.getByTestId("fit-pack").textContent).toMatch(/false/);
    });
  });
});
