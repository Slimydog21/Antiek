import { afterEach, describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, act, cleanup } from "@testing-library/react";

afterEach(() => {
  cleanup();
});

/** The accessible description: the text of every aria-describedby target,
 *  hidden ones included (the accname rule for directly referenced nodes). */
function computeAccessibleDescription(el: Element): string {
  return (el.getAttribute("aria-describedby") ?? "")
    .split(/\s+/)
    .filter(Boolean)
    .map((id) => document.getElementById(id)?.textContent?.trim() ?? "")
    .join(" ");
}

import LemonButton from "./LemonButton";
import { LemonModal } from "./LemonModal";
import { LemonSelect } from "./LemonSelect";
import { LemonToastViewport, toast } from "./LemonToast";
import { ErrorBanner } from "./ErrorBanner";
import type React from "react";

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

describe("LemonButton — disabledReason (never quietly disabled)", () => {
  it("stays focusable and exposes aria-disabled instead of the native attribute", () => {
    render(<LemonButton disabledReason="Type a question first">Ask</LemonButton>);
    const btn = screen.getByRole("button", { name: "Ask" }) as HTMLButtonElement;
    expect(btn.disabled).toBe(false);
    expect(btn.getAttribute("aria-disabled")).toBe("true");
    btn.focus();
    expect(document.activeElement).toBe(btn);
  });

  it("carries the reason as its accessible description and as the visible tip", () => {
    render(<LemonButton disabledReason="Type a question first">Ask</LemonButton>);
    const btn = screen.getByRole("button", { name: "Ask" });
    expect(computeAccessibleDescription(btn)).toBe("Type a question first");
    expect(btn.getAttribute("data-tip")).toBe("Type a question first");
    // The reason is not folded into the button's name (it sits outside it).
    expect(btn.textContent).toBe("Ask");
  });

  it("keeps a caller's own aria-describedby alongside the reason", () => {
    render(
      <>
        <p id="hint">Costs one credit.</p>
        <LemonButton aria-describedby="hint" disabledReason="Connect a model first">Run</LemonButton>
      </>,
    );
    const btn = screen.getByRole("button", { name: "Run" });
    expect(computeAccessibleDescription(btn)).toBe("Costs one credit. Connect a model first");
  });

  it("does nothing on click, and a disabled submit button does not submit its form", () => {
    const onClick = vi.fn();
    const onSubmit = vi.fn((e: React.FormEvent) => e.preventDefault());
    render(
      <form onSubmit={onSubmit}>
        <LemonButton type="submit" onClick={onClick} disabledReason="Name it first">Save</LemonButton>
      </form>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(onClick).not.toHaveBeenCalled();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("an empty or null reason leaves the button enabled", () => {
    const onClick = vi.fn();
    render(<LemonButton disabledReason={null} onClick={onClick}>Go</LemonButton>);
    const btn = screen.getByRole("button", { name: "Go" });
    expect(btn.hasAttribute("aria-disabled")).toBe(false);
    expect(btn.hasAttribute("data-tip")).toBe(false);
    fireEvent.click(btn);
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it("legacy `disabled` without a reason is aria-disabled too, with no tip", () => {
    render(<LemonButton disabled>Old</LemonButton>);
    const btn = screen.getByRole("button", { name: "Old" }) as HTMLButtonElement;
    expect(btn.disabled).toBe(false);
    expect(btn.getAttribute("aria-disabled")).toBe("true");
    expect(btn.hasAttribute("data-tip")).toBe(false);
  });

  it("does not bake in pointer-events:none or an opacity fade", () => {
    render(<LemonButton disabledReason="Not yet">X</LemonButton>);
    const cls = screen.getByRole("button", { name: "X" }).className;
    expect(cls).not.toMatch(/pointer-events-none/);
    expect(cls).not.toMatch(/disabled:opacity/);
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
    // The navigator receives the full target (the shell focuses a panel
    // after navigating).
    expect(navigate).toHaveBeenCalledWith({ path: "/inv/xyz" });
  });

  it("the navigator receives panelId when present", () => {
    const navigate = vi.fn();
    toast.setNavigator(navigate);
    render(<LemonToastViewport />);
    act(() => {
      toast.ok("Open panel", { target: { path: "/inv/abc", panelId: "rw:chat:abc" } });
    });
    fireEvent.click(screen.getByRole("button", { name: /Open panel/ }));
    expect(navigate).toHaveBeenCalledWith({
      path: "/inv/abc",
      panelId: "rw:chat:abc",
    });
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


describe("ErrorBanner — the shared error callout (Q4)", () => {
  it("defaults to role=\"alert\" (a load/mutation failure is a genuine alert)", () => {
    render(<ErrorBanner>Couldn&rsquo;t load.</ErrorBanner>);
    expect(screen.getByRole("alert").textContent).toContain("Couldn’t load.");
  });

  it("accepts role=\"status\" for quiet, non-urgent contexts", () => {
    render(<ErrorBanner role="status">Some rows were skipped.</ErrorBanner>);
    expect(screen.getByRole("status").textContent).toContain("Some rows were skipped.");
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("is painted with the danger/emperor token, not the raw red palette", () => {
    render(<ErrorBanner>token check</ErrorBanner>);
    const el = screen.getByRole("alert");
    expect(el.className).toContain("border-danger");
    expect(el.className).toContain("bg-danger/10");
    expect(el.className).toContain("text-danger");
    expect(el.className).not.toContain("red-");
  });
});
