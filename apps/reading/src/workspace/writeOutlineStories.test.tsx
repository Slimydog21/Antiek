/**
 * The outline-pane stories mount and show what each claims, and the drop
 * payload parser refuses everything that is not a source document
 * (forensic defect 11). Storybook itself is not in the test run.
 */
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render } from "@testing-library/react";

import * as stories from "./WriteOutlinePane.stories";
import { parseSourceDragPayload } from "./WriteOutlinePane";

afterEach(() => {
  cleanup();
  document.body.innerHTML = "";
});

type StoryModule = typeof stories;
const Component = stories.default.component;

function mount(name: keyof StoryModule) {
  const story = stories[name] as { args?: { state?: "no-sources" | "sources" | "refused" } };
  return render(<Component state={story.args?.state ?? "no-sources"} />);
}

describe("WriteOutlinePane stories", () => {
  const names = Object.keys(stories).filter((k) => k !== "default") as (keyof StoryModule)[];

  it("every story mounts with its block card", () => {
    expect(names).toHaveLength(6);
    for (const name of names) {
      mount(name);
      expect(document.querySelector("[data-block-card]"), String(name)).toBeTruthy();
      cleanup();
    }
  });

  it("no sources: the session-state copy, with no internal file name", () => {
    mount("NoSourcesNight");
    const text = document.querySelector("[data-no-sources]")!.textContent ?? "";
    expect(text).toContain("session state");
    expect(text).not.toMatch(/\.tsx?\b|TODO/);
  });

  it("refused: the note says what happened and that nothing was assigned", () => {
    mount("DropRefusedDay");
    const note = document.querySelector("[data-drop-refused]")!;
    expect(note.getAttribute("role")).toBe("status");
    expect(note.textContent).toMatch(/wasn.t a source document/);
    expect(note.textContent).toMatch(/nothing was assigned/);
  });

  it("sources: each assigned document by title, with its remove control", () => {
    mount("SourcesDay");
    expect(document.querySelectorAll("[data-assigned-sources] li")).toHaveLength(2);
    expect(document.body.textContent).toContain("The Beak of the Finch");
  });
});

describe("parseSourceDragPayload", () => {
  it("accepts a source document, trimming the id and the title", () => {
    expect(parseSourceDragPayload(JSON.stringify({ document_id: " doc-1 ", document_title: " A Book " }))).toEqual({
      document_id: "doc-1",
      document_title: "A Book",
    });
  });

  it("a missing, blank or non-string title reads as none", () => {
    for (const title of [undefined, "   ", 7, null]) {
      expect(parseSourceDragPayload(JSON.stringify({ document_id: "d", document_title: title }))).toEqual({
        document_id: "d",
        document_title: null,
      });
    }
  });

  it.each([
    ["malformed JSON", "{"],
    ["a number", "42"],
    ["null", "null"],
    ["an array", JSON.stringify([{ document_id: "d" }])],
    ["no id", JSON.stringify({ document_title: "t" })],
    ["a numeric id", JSON.stringify({ document_id: 12 })],
    ["a blank id", JSON.stringify({ document_id: "  " })],
  ])("refuses %s", (_label, raw) => {
    expect(parseSourceDragPayload(raw)).toBeNull();
  });
});
