/**
 * Pure unit tests for domainSearchDefaults (residual alq).
 * No React — guarantees HostedHtml/Marketplace import path stays pure.
 */
import { describe, expect, it } from "vitest";
import {
  domainAwareSearchDefault,
  domainSearchCoverage,
  formatResearchDomainsClause,
  normalizeDomainSubjects,
} from "./domainSearchDefaults";

describe("domainSearchDefaults pure module (alq)", () => {
  it("maps free PD spine subjects with precedence", () => {
    expect(domainAwareSearchDefault(["heat", "engineering"])).toMatch(
      /heat signal processing/i,
    );
    expect(domainAwareSearchDefault(["economics", "philosophy"])).toMatch(
      /economics wealth nations/i,
    );
    expect(domainAwareSearchDefault(["literature"])).toMatch(
      /literature novel manners/i,
    );
    expect(domainAwareSearchDefault(["science"])).toMatch(
      /science natural philosophy/i,
    );
    expect(domainAwareSearchDefault(["biology", "science"])).toMatch(
      /biology instruments micrographia/i,
    );
    expect(domainAwareSearchDefault([])).toBe("");
    expect(domainAwareSearchDefault(null)).toBe("");
  });

  it("reports coverage without inventing defaults for unknown tags", () => {
    const cov = domainSearchCoverage([
      "heat",
      "signal_processing",
      "unknown_tag",
    ]);
    expect(cov.has_default).toBe(true);
    expect(cov.covered).toEqual(
      expect.arrayContaining(["heat", "signal_processing"]),
    );
    expect(cov.uncovered).toContain("unknown_tag");
    expect(domainSearchCoverage(["totally_unknown"]).has_default).toBe(false);
    expect(domainSearchCoverage(["totally_unknown"]).default_query).toBe("");
  });

  it("normalizes domain subjects and formats research_domains clause (aod)", () => {
    expect(normalizeDomainSubjects(["Heat", "signal_processing", "heat", "  "])).toEqual([
      "heat",
      "signal_processing",
    ]);
    expect(normalizeDomainSubjects(null)).toEqual([]);
    expect(normalizeDomainSubjects([])).toEqual([]);
    expect(formatResearchDomainsClause(["Heat", "signal_processing", "heat"])).toBe(
      " · research_domains=heat,signal_processing",
    );
    expect(formatResearchDomainsClause(null)).toBe("");
    expect(formatResearchDomainsClause([])).toBe("");
  });
});
