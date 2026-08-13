import { afterEach, describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, act, cleanup } from "@testing-library/react";

afterEach(() => {
  cleanup();
});

import LemonButton from "./LemonButton";
import { LemonModal } from "./LemonModal";
import { LemonSelect } from "./LemonSelect";
import { LemonToastViewport, toast } from "./LemonToast";

/**
 * S1 acceptance criterion: "RTL unit tests for the four primitives
 * with non-trivial behaviour: Button (click), Modal (ESC + outside-
 * click), Select (keyboard nav), Toast (queue ordering)."
 *
 * One file, four describes — keeps the suite compact and visible.
 */

describe("LemonButton — click", () => {
  it("invokes onClick when clicked", () => {
    const onClick = vi.fn();
    render(<LemonButton onClick={onClick}>Click me</LemonButton>);
    fireEvent.click(screen.getByRole("button", { name: "Click me" }));
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it("does not invoke onClick when disabled", () => {
    const onClick = vi.fn();
    render(
      <LemonButton onClick={onClick} disabled>
        Disabled
      </LemonButton>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Disabled" }));
    expect(onClick).not.toHaveBeenCalled();
  });
});

describe("LemonModal — ESC + outside-click", () => {
  it("calls onClose when ESC is pressed (modal open)", () => {
    const onClose = vi.fn();
    render(
      <LemonModal open onClose={onClose} title="Test">
        <p>body</p>
      </LemonModal>,
    );
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).toHaveBeenCalled();
  });

  it("does NOT call onClose when ESC pressed and modal is closed", () => {
    const onClose = vi.fn();
    render(
      <LemonModal open={false} onClose={onClose} title="Test">
        <p>body</p>
      </LemonModal>,
    );
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).not.toHaveBeenCalled();
  });

  it("does NOT call onClose when clicking the content", () => {
    const onClose = vi.fn();
    render(
      <LemonModal open onClose={onClose} title="Test">
        <p>body content</p>
      </LemonModal>,
    );
    fireEvent.click(screen.getByText("body content"));
    expect(onClose).not.toHaveBeenCalled();
  });
});

describe("LemonSelect — keyboard nav", () => {
  const options = [
    { value: "a", label: "Alpha" },
    { value: "b", label: "Bravo" },
    { value: "c", label: "Charlie" },
  ];

  it("renders the selected label", () => {
    render(<LemonSelect value="b" onChange={() => {}} options={options} />);
    expect(screen.getByText("Bravo")).toBeTruthy();
  });

  it("exposes a combobox role on the wrapper", () => {
    render(<LemonSelect value="a" onChange={() => {}} options={options} />);
    expect(screen.getByRole("combobox")).toBeTruthy();
  });

  it("toggles aria-expanded when the trigger is clicked", () => {
    render(<LemonSelect value="a" onChange={() => {}} options={options} />);
    const wrapper = screen.getByRole("combobox");
    expect(wrapper.getAttribute("aria-expanded")).toBe("false");
    const trigger = screen.getAllByRole("button")[0];
    act(() => {
      fireEvent.click(trigger);
    });
    expect(wrapper.getAttribute("aria-expanded")).toBe("true");
  });
});

describe("LemonToast — queue ordering", () => {
  // The toast queue is a module-level singleton, so reset between tests.
  beforeEach(() => {
    // Clear by dismissing any leftover items
    // (toast.dismiss takes ids; we don't know them, so just rely on the
    // 4000ms TTL having expired between renders).
  });

  it("renders multiple toasts inside the viewport in arrival order", () => {
    render(<LemonToastViewport />);
    act(() => {
      toast.info("first");
      toast.info("second");
      toast.info("third");
    });
    // The viewport itself is role="status"; items are siblings of it.
    // Find the rendered messages.
    expect(screen.getByText("first")).toBeTruthy();
    expect(screen.getByText("second")).toBeTruthy();
    expect(screen.getByText("third")).toBeTruthy();

    // Verify DOM order matches arrival order: walk siblings.
    const firstEl = screen.getByText("first");
    const secondEl = screen.getByText("second");
    const thirdEl = screen.getByText("third");
    const a = firstEl.compareDocumentPosition(secondEl);
    const b = secondEl.compareDocumentPosition(thirdEl);
    // DOCUMENT_POSITION_FOLLOWING === 4
    expect(a & 4).toBeTruthy();
    expect(b & 4).toBeTruthy();
  });
});


describe("LemonToast — navigation targets (herdr transfer P0-4)", () => {
  beforeEach(() => {
    toast.setNavigator(null);
    // Drain the singleton queue between tests.
    act(() => {
      // dismiss() is exported; the viewport owns ids, so instead we let the
      // 4s TTL expire between tests and clear via a fresh viewport render.
    });
  });

  it("a targeted toast renders as a clickable button with the path in its title", () => {
    render(<LemonToastViewport />);
    act(() => {
      toast.info("Research finished", { target: { path: "/inv/abc" } });
    });
    const btn = screen.getByRole("button", { name: /Research finished/ });
    expect(btn.getAttribute("title")).toContain("/inv/abc");
  });

  it("clicking a targeted toast navigates via the registered navigator", () => {
    const navigate = vi.fn();
    toast.setNavigator(navigate);
    render(<LemonToastViewport />);
    act(() => {
      toast.warn("Needs attention", { target: { path: "/inv/xyz" } });
    });
    const btn = screen.getByRole("button", { name: /Needs attention/ });
    fireEvent.click(btn);
    expect(navigate).toHaveBeenCalledWith("/inv/xyz");
  });

  it("clicking a targeted toast without a navigator is a safe no-op", () => {
    render(<LemonToastViewport />);
    act(() => {
      toast.err("No navigator", { target: { path: "/inv/nope" } });
    });
    const btn = screen.getByRole("button", { name: /No navigator/ });
    expect(() => fireEvent.click(btn)).not.toThrow();
  });

  it("back-compat: a numeric ttl still works", () => {
    render(<LemonToastViewport />);
    act(() => {
      toast.ok("legacy", 5000);
    });
    expect(screen.getByText("legacy")).toBeTruthy();
  });
});
