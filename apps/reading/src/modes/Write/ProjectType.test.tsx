import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { ProjectTypeField, resolveKind } from "./ProjectType";

/**
 * ProjectType.test — open-ended type, presets SEED not GATE (SPR-09 M4).
 *
 * rigor #3d: a project type the AI has never seen must NOT crash or snap to a
 * hidden hardcoded shape. A novel type resolves to general_essay (the OPEN
 * default — no fixed section skeleton), so the inferred outline shape is
 * non-crashing and unconstrained.
 */

afterEach(cleanup);

describe("resolveKind — presets seed, novelty is open", () => {
  it("maps presets to their kind", () => {
    expect(resolveKind("Research memo")).toBe("research_memo");
    expect(resolveKind("Book chapter")).toBe("book_chapter");
    expect(resolveKind("Biography section")).toBe("biography_section");
    expect(resolveKind("Investor brief")).toBe("investor_brief");
    expect(resolveKind("Essay")).toBe("general_essay");
  });

  it("rigor #3d — a NOVEL type falls to general_essay, never crashes or gates", () => {
    // Types the AI has never seen — none of these throw, none snap to a memo /
    // chapter template; they land on the open default.
    expect(resolveKind("a wedding toast")).toBe("general_essay");
    expect(resolveKind("grant rebuttal")).toBe("general_essay");
    expect(resolveKind("")).toBe("general_essay");
    expect(resolveKind("   ")).toBe("general_essay");
    expect(resolveKind("🎤 spoken-word piece")).toBe("general_essay");
  });

  it("loose keyword seeding still lands a near-match (non-gating)", () => {
    expect(resolveKind("internal memo on pricing")).toBe("research_memo");
    expect(resolveKind("chapter 3 draft")).toBe("book_chapter");
  });
});

describe("ProjectTypeField — freeform input + preset chips", () => {
  it("typing a novel type reports it with the open kind", async () => {
    const onChange = vi.fn();
    render(
      <ProjectTypeField value={{ freeform: "", kind: "general_essay" }} onChange={onChange} />,
    );
    await userEvent.type(screen.getByPlaceholderText(/what kind of piece/i), "wedding toast");
    // The last call carries the freeform text + the resolved (open) kind.
    const last = onChange.mock.calls.at(-1)?.[0];
    expect(last.freeform).toContain("toast");
    expect(last.kind).toBe("general_essay");
  });

  it("a preset chip seeds the kind", async () => {
    const onChange = vi.fn();
    render(
      <ProjectTypeField value={{ freeform: "", kind: "general_essay" }} onChange={onChange} />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Research memo" }));
    expect(onChange).toHaveBeenLastCalledWith({ freeform: "Research memo", kind: "research_memo" });
  });
});
