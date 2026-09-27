import { useState } from "react";
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";

import { LemonModal } from "./LemonModal";
import { LemonSelect } from "./LemonSelect";

afterEach(cleanup);

function DialogStack({ forceTop = false, showOlder = true }: { forceTop?: boolean; showOlder?: boolean }) {
  const [olderOpen, setOlderOpen] = useState(true);
  const [newerOpen, setNewerOpen] = useState(true);
  return <>
    {showOlder && <LemonModal open={olderOpen} title="Project" onClose={() => setOlderOpen(false)}>
      <p>Project content</p>
    </LemonModal>}
    <LemonModal open={newerOpen} title="Shortcuts" forceUserAction={forceTop} onClose={() => setNewerOpen(false)}>
      <LemonSelect aria-label="Scope" value="all" onChange={() => {}} options={[
        { value: "all", label: "All actions" },
        { value: "reading", label: "Reading" },
      ]} />
    </LemonModal>
  </>;
}

describe("LemonModal nested Escape ownership", () => {
  it.each(["dialog", "body"])("closes the newest dialog first when Escape targets %s", (target) => {
    render(<DialogStack />);
    const newer = screen.getByRole("dialog", { name: "Shortcuts" });
    if (target === "body" && document.activeElement instanceof HTMLElement) document.activeElement.blur();
    fireEvent.keyDown(target === "body" ? document.body : newer, { key: "Escape" });
    expect(screen.queryByRole("dialog", { name: "Shortcuts" })).toBeNull();
    expect(screen.queryByRole("dialog", { name: "Project" })).not.toBeNull();
    fireEvent.keyDown(document.body, { key: "Escape" });
    expect(screen.queryByRole("dialog", { name: "Project" })).toBeNull();
  });

  it("does not dismiss an older dialog behind a top dialog that requires user action", () => {
    render(<DialogStack forceTop />);
    const newer = screen.getByRole("dialog", { name: "Shortcuts" });
    fireEvent.keyDown(newer, { key: "Escape" });
    fireEvent.keyDown(document.body, { key: "Escape" });
    expect(screen.queryByRole("dialog", { name: "Project" })).not.toBeNull();
    expect(screen.queryByRole("dialog", { name: "Shortcuts" })).not.toBeNull();
    expect(newer.contains(document.activeElement)).toBe(true);
  });

  it("lets a select inside the newest dialog consume Escape before either dialog closes", () => {
    render(<DialogStack />);
    const newer = screen.getByRole("dialog", { name: "Shortcuts" });
    fireEvent.click(within(newer).getByRole("button", { name: /All actions/ }));
    expect(screen.queryByRole("listbox")).not.toBeNull();
    fireEvent.keyDown(document.activeElement ?? document.body, { key: "Escape" });
    expect(screen.queryByRole("listbox")).toBeNull();
    expect(screen.getAllByRole("dialog")).toHaveLength(2);
    fireEvent.keyDown(newer, { key: "Escape" });
    expect(screen.queryByRole("dialog", { name: "Shortcuts" })).toBeNull();
    expect(screen.queryByRole("dialog", { name: "Project" })).not.toBeNull();
  });

  it("keeps focus in the newest dialog when an older dialog unmounts", () => {
    const { rerender } = render(<DialogStack />);
    const newer = screen.getByRole("dialog", { name: "Shortcuts" });
    const focused = within(newer).getByRole("button", { name: /All actions/ });
    focused.focus();
    rerender(<DialogStack showOlder={false} />);
    expect(document.activeElement).toBe(focused);
    expect(screen.queryByRole("dialog", { name: "Project" })).toBeNull();
  });
});
