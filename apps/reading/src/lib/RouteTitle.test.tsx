/**
 * FFX SPR-01 M4 (A-13) — per-route document titles.
 *
 * The crawl saw document.title === "Antiek — reading" on 369/369 visits; only
 * the popout window (PanelWindowApp) ever set a title. RouteTitle names the
 * page from the taxonomy the shell already owns (MODE_TAXONOMY).
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { act, cleanup, render } from "@testing-library/react";
import { MemoryRouter, useNavigate } from "react-router-dom";
import { useEffect } from "react";

import { MODE_TAXONOMY } from "../shell/workflowTaxonomy";
import { RouteTitle, routeNameFor, titleFor } from "./RouteTitle";

function labelOf(route: string): string {
  const entry = MODE_TAXONOMY.find((m) => m.route === route);
  if (!entry) throw new Error(`taxonomy has no route ${route}`);
  return entry.label;
}

function mountAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <RouteTitle />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  document.title = "Antiek — reading";
});

afterEach(cleanup);

describe("RouteTitle (A-13)", () => {
  it("/notebooks → the taxonomy's Notebooks name", () => {
    mountAt("/notebooks");
    expect(document.title).toBe(`${labelOf("/notebooks")} · Antiek`);
    expect(document.title).toBe("Notebooks · Antiek");
  });

  it("/unknown → Antiek", () => {
    mountAt("/unknown");
    expect(document.title).toBe("Antiek");
  });

  it("parameterised routes resolve by pattern, not string equality (/read/:documentId)", () => {
    mountAt("/read/doc-upload-24e63b6fb9eea860");
    expect(document.title).toBe(`${labelOf("/read/:documentId")} · Antiek`);
  });

  it("the most specific pattern wins (/speak/invite/:token over /speak/:projectId), and a static route beats a pattern (/speak/browse)", () => {
    expect(routeNameFor("/speak/invite/abc")).toBe(labelOf("/speak/invite/:token"));
    expect(routeNameFor("/speak/browse")).toBe(labelOf("/speak/browse"));
    expect(routeNameFor("/speak/p-123")).toBe(labelOf("/speak/:projectId"));
  });

  it("a route two modes share names the workflow (/write → Write, /speak → Speak)", () => {
    expect(routeNameFor("/write")).toBe("Write");
    expect(routeNameFor("/speak")).toBe("Speak");
  });

  it("an un-taxonomised child route falls back to its routed parent (/write/:deliverableId → Write)", () => {
    expect(titleFor("/write/dlv-18f347d18ee748a0")).toBe("Write · Antiek");
    expect(titleFor("/deep-research/s-1")).toBe(`${labelOf("/deep-research")} · Antiek`);
  });

  it("a trailing slash does not change the answer", () => {
    expect(titleFor("/notebooks/")).toBe("Notebooks · Antiek");
  });

  it("updates on navigation", () => {
    let go: (to: string) => void = () => {};
    function Nav() {
      const navigate = useNavigate();
      useEffect(() => {
        go = navigate;
      }, [navigate]);
      return null;
    }
    render(
      <MemoryRouter initialEntries={["/library"]}>
        <Nav />
        <RouteTitle />
      </MemoryRouter>,
    );
    expect(document.title).toBe("Library · Antiek");
    act(() => go("/settings"));
    expect(document.title).toBe("Settings · Antiek");
  });

  it("leaves popout windows (/_panel/:panelId) to PanelWindowApp's own title", () => {
    document.title = "antiek · popout · Notes";
    mountAt("/_panel/p1");
    expect(document.title).toBe("antiek · popout · Notes");
  });

  it("names at least 20 distinct pages across the App.tsx route table (the crawl saw 1)", () => {
    const app = readFileSync(join(__dirname, "..", "App.tsx"), "utf8");
    const paths = [...app.matchAll(/path="([^"]+)"/g)]
      .map((m) => m[1])
      .filter((p) => p !== "*" && !p.startsWith("/_panel"))
      .map((p) => p.replace(/:[A-Za-z]+/g, "x1"));
    expect(paths.length).toBeGreaterThan(50);
    const titles = new Set(paths.map(titleFor));
    expect(titles.size).toBeGreaterThanOrEqual(20);
  });
});
