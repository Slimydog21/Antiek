import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { MemoryRouter } from "react-router-dom";

import { OPERATOR_ROUTES } from "../../shell/operatorRoutes";
import Topbar from "./Topbar";

afterEach(() => {
  cleanup();
});

describe("Topbar", () => {
  it.each(OPERATOR_ROUTES.filter((route) => route.path !== "/").map((route) => [
    route.path,
    route.title,
  ]))("uses the shared operator route title for %s", (path, expected) => {
    render(
      <MemoryRouter initialEntries={[path]}>
        <Topbar />
      </MemoryRouter>,
    );

    expect(screen.getByRole("navigation", { name: "Breadcrumb" })).toBeTruthy();
    expect(screen.getByText(expected)).toBeTruthy();
  });

  it("uses the canonical privacy dashboard breadcrumb label", () => {
    render(
      <MemoryRouter initialEntries={["/privacy"]}>
        <Topbar />
      </MemoryRouter>,
    );

    expect(screen.getByRole("navigation", { name: "Breadcrumb" })).toBeTruthy();
    expect(screen.getByText("Privacy dashboard")).toBeTruthy();
    expect(screen.queryByText(/^Privacy$/)).toBeNull();
  });

  it("uses the canonical substrate stats breadcrumb label", () => {
    render(
      <MemoryRouter initialEntries={["/stats"]}>
        <Topbar />
      </MemoryRouter>,
    );

    expect(screen.getByRole("navigation", { name: "Breadcrumb" })).toBeTruthy();
    expect(screen.getByText("Substrate stats")).toBeTruthy();
    expect(screen.queryByText(/^Stats$/)).toBeNull();
  });

  it.each([
    ["/operator", "Operator dashboard", /^Operator$/],
    ["/outcomes", "Outcomes audit", /^Outcomes$/],
    ["/payouts", "Payouts audit", /^Payouts$/],
    ["/loop-3", "Loop 3 checklist", /^Loop 3$/],
    ["/skill-rules", "Skill rules", /^Skill Rules$/],
    ["/federation", "Federation config", /^Federation$/],
    ["/map", "Application map", /^Map$/],
    ["/coordination", "Coordination", /^coordination$/],
    ["/marketplace", "Marketplace metrics", /^marketplace$/],
    ["/settings", "Settings", /^settings$/],
    ["/login", "Login", /^login$/],
  ])("uses the canonical shared-surface breadcrumb label for %s", (path, expected, oldLabel) => {
    render(
      <MemoryRouter initialEntries={[path]}>
        <Topbar />
      </MemoryRouter>,
    );

    expect(screen.getByRole("navigation", { name: "Breadcrumb" })).toBeTruthy();
    expect(screen.getByText(expected)).toBeTruthy();
    expect(screen.queryByText(oldLabel)).toBeNull();
  });

  it.each([
    ["/operator/advertiser-campaigns", "Advertiser console", /advertiser-campaigns/],
    ["/operator/payouts/dashboard", "Payout dashboard", /Payouts audit/],
    ["/me/payouts", "Creator payouts", /Payouts audit/],
    ["/cross-graph/citations", "Cross-graph citations", /^Cross-graph$/],
    ["/coordination/cost-consent", "Cost & consent", /cost-consent/],
  ])("uses the exact canonical breadcrumb label for %s", (path, expected, wrongLabel) => {
    render(
      <MemoryRouter initialEntries={[path]}>
        <Topbar />
      </MemoryRouter>,
    );

    expect(screen.getByRole("navigation", { name: "Breadcrumb" })).toBeTruthy();
    expect(screen.getByText(expected)).toBeTruthy();
    expect(screen.queryByText(wrongLabel)).toBeNull();
  });
});
