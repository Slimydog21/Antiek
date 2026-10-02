/**
 * FFX SPR-01 M5 (A-18, breadcrumb half) — crumbs speak the product's words.
 *
 * The crawl read raw slugs and ids in the crumb row: "home", "my-research",
 * "write › dlv-18f347d18ee748a0". Crumbs now resolve through the same
 * taxonomy lookup as the tab title (lib/RouteTitle.tsx) and show an id as
 * its entity noun, never the id.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { Breadcrumbs, breadcrumbsFor } from "./Breadcrumbs";
import { routeNameFor } from "../../lib/RouteTitle";

afterEach(cleanup);

function labels(pathname: string): string[] {
  return breadcrumbsFor(pathname).map((c) => c.label);
}

function renderedTrail(pathname: string): string {
  render(
    <MemoryRouter initialEntries={[pathname]}>
      <Breadcrumbs pathname={pathname} />
    </MemoryRouter>,
  );
  const items = screen.getAllByRole("listitem").map((li) => (li.textContent ?? "").replace("›", "").trim());
  return items.join(" › ");
}

describe("Breadcrumbs (A-18)", () => {
  it("/write/dlv-18f347d18ee748a0 renders 'Write › a piece', never the id", () => {
    expect(renderedTrail("/write/dlv-18f347d18ee748a0")).toBe("Write › a piece");
    expect(document.body.textContent).not.toContain("dlv-");
  });

  it("the crawl's other raw slugs read as words", () => {
    expect(labels("/home")).toEqual(["Home"]);
    expect(labels("/my-research")).toEqual(["My research"]);
    expect(labels("/")).toEqual(["Research"]);
  });

  it("each id becomes its entity noun", () => {
    expect(labels("/notebook/nb-1cfb80ea404b")).toEqual(["Notebook", "a notebook"]);
    expect(labels("/inv/inv-35c0825e359a")).toEqual(["Research", "a research"]);
    expect(labels("/read/doc-upload-24e63b6fb9eea860")).toEqual(["Reader", "a document"]);
    // "/read" is not a page of its own, so its crumb names the mode but does not link.
    expect(breadcrumbsFor("/read/doc-upload-24e63b6fb9eea860")[0].to).toBeUndefined();
    expect(labels("/outcomes/syn-8f2a91")).toEqual(["Outcomes audit", "an outcome"]);
    expect(labels("/deep-research/5f0c1e2a")).toEqual(["Deep Research Workspace", "a research"]);
  });

  it("a word in a parameter slot stays a word, unlinked (it is not a record)", () => {
    expect(labels("/speak/invite/tok-0a9f33")).toEqual(["Speak", "Invite", "an invitation"]);
    expect(breadcrumbsFor("/speak/invite/tok-0a9f33")[1].to).toBeUndefined();
    expect(labels("/notebook/auto")).toEqual(["Notebook", "Auto"]);
  });

  it("uses the same names as the tab title (one lookup, shared with lib/RouteTitle)", () => {
    for (const path of ["/notebooks", "/library", "/settings", "/write", "/speak", "/loop-3"]) {
      expect(labels(path)).toEqual([routeNameFor(path)]);
    }
  });

  it("every crumb but the last links to its own path", () => {
    const crumbs = breadcrumbsFor("/write/dlv-18f347d18ee748a0");
    expect(crumbs[0]).toMatchObject({ label: "Write", to: "/write" });
    render(
      <MemoryRouter>
        <Breadcrumbs pathname="/write/dlv-18f347d18ee748a0" />
      </MemoryRouter>,
    );
    expect(screen.getByRole("link", { name: "Write" }).getAttribute("href")).toBe("/write");
    expect(screen.queryByRole("link", { name: "a piece" })).toBeNull();
  });

  it("no route in App.tsx, filled with realistic ids, ever shows an id-shaped crumb", () => {
    const app = readFileSync(join(__dirname, "..", "..", "App.tsx"), "utf8");
    const sample: Record<string, string> = {
      documentId: "doc-upload-24e63b6fb9eea860",
      notebookId: "nb-1cfb80ea404b",
      investigationId: "inv-35c0825e359a",
      deliverableId: "dlv-18f347d18ee748a0",
      synthesisId: "syn-8f2a91c0",
      sessionId: "5f0c1e2a9b",
      assetId: "asset-7c1d",
      projectId: "proj-91ab22",
      token: "tok-0a9f33",
      ruleId: "rule-44",
      interviewId: "iv-123",
      kind: "claim",
      id: "c-77e1",
      panelId: "p1",
    };
    const paths = [...app.matchAll(/path="([^"]+)"/g)]
      .map((m) => m[1])
      .filter((p) => p !== "*")
      .map((p) => p.replace(/:([A-Za-z]+)/g, (_, name: string) => sample[name] ?? "x-9f8e7d"));
    expect(paths.length).toBeGreaterThan(50);
    for (const path of paths) {
      for (const label of labels(path)) {
        for (const id of Object.values(sample)) {
          expect(label, `${path} → "${label}"`).not.toContain(id);
        }
        // An id-shaped token: letters, a hyphen, then a hex run with a digit.
        expect(label, `${path} → "${label}"`).not.toMatch(/\b[a-z]+-[0-9a-f]*\d[0-9a-f]*\b/i);
      }
    }
  });
});
