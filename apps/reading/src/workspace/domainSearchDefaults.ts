/**
 * domainSearchDefaults — pure domain-aware intelligent twin-search defaults.
 * Residual (alo): extracted from ResearchContextPanel so HostedHtml / Marketplace
 * can import without vitest mock collisions on the panel module.
 */

/**
 * Residual (ahr/aiy/akq): domain-aware intelligent-search default from asset subjects
 * (e.g. free STEM Fourier heat/signal_processing → grounded twin search query).
 * Never invents subjects; empty when no domain match.
 * Residual (aiy): biology / method / physics / mathematics free STEM pairs.
 * Residual (akq): free PD economics / politics / philosophy / engineering pairs
 * (Wealth of Nations · Federalist · Discourse/Liberty · Heaviside engineering)
 * so intelligent search covers the full offline marketplace subject spine.
 * Residual (akw): free PD literature + bare technology (Pride · tech spine when
 * not already matched by computing/electricity/heat).
 * Residual (alf): bare science catch-all.
 * Residual (alj): domainSearchCoverage for honesty stamps (covered vs uncovered).
 */
export function domainAwareSearchDefault(
  subjects?: readonly string[] | null,
): string {
  const set = new Set(
    (subjects || []).map((s) => String(s || "").trim().toLowerCase()).filter(Boolean),
  );
  if (set.has("heat") || set.has("signal_processing")) {
    return "heat signal processing mathematical laws twin insights";
  }
  if (set.has("foundations") || set.has("computability") || set.has("logic")) {
    return "foundations incompleteness computability twin insights";
  }
  if (set.has("electricity") || set.has("electromagnetism")) {
    return "electricity electromagnetism induction twin insights";
  }
  if (set.has("information_theory") || set.has("communication")) {
    return "information theory communication twin insights";
  }
  if (set.has("computing") || set.has("history")) {
    return "computing analytical engine twin insights";
  }
  // Residual (aiy): free biology STEM (Origin + Hooke Micrographia).
  if (set.has("biology") || set.has("instruments")) {
    return "biology instruments micrographia natural history twin insights";
  }
  // Residual (aiy): method / Baconian Novum Organum + instrumented observation.
  // Precedence over bare philosophy (Novum carries philosophy+method).
  if (set.has("method") || set.has("observation")) {
    return "method observation novum organum twin insights";
  }
  // Residual (aiy): physics STEM (Principia / Faraday physics tags).
  if (set.has("physics") && !set.has("electricity") && !set.has("electromagnetism")) {
    return "physics motion forces principia twin insights";
  }
  // Residual (aiy): pure mathematics STEM (Euclid Elements).
  if (set.has("mathematics") && !set.has("physics") && !set.has("computing")) {
    return "mathematics geometry elements axioms twin insights";
  }
  // Residual (akq): free PD economics (Wealth of Nations).
  if (set.has("economics") || set.has("political_economy")) {
    return "economics wealth nations labour markets twin insights";
  }
  // Residual (akq): free PD politics (Federalist Papers).
  if (set.has("politics") || set.has("government") || set.has("constitution")) {
    return "politics constitution federalist government twin insights";
  }
  // Residual (akq): free PD philosophy when method did not already match
  // (Discourse on the Method · On Liberty · Mill/Descartes spine).
  if (set.has("philosophy") || set.has("liberty") || set.has("ethics")) {
    return "philosophy liberty discourse method twin insights";
  }
  // Residual (akq): engineering when electricity/heat did not already match
  // (Heaviside EM engineering tags; Fourier engineering yields to heat above).
  if (set.has("engineering") || set.has("electrical_engineering")) {
    return "engineering electromagnetic operational calculus twin insights";
  }
  // Residual (akw): free PD literature (Pride and Prejudice · Austen spine).
  if (set.has("literature") || set.has("fiction") || set.has("novel")) {
    return "literature novel manners society twin insights";
  }
  // Residual (akw): bare technology when computing/electricity/heat did not match
  // (catalog tech tags on Faraday/Hooke/Boole still yield earlier STEM defaults).
  if (set.has("technology") || set.has("tech")) {
    return "technology instruments research methods twin insights";
  }
  // Residual (alf): bare science when no more-specific STEM domain matched
  // (catch-all for free PD science spine after physics/biology/math/etc.).
  if (set.has("science") || set.has("natural_philosophy")) {
    return "science natural philosophy research methods twin insights";
  }
  return "";
}

/**
 * Residual (alj): report which asset subjects map to a domain-aware twin-search
 * default vs remain uncovered (honest empty default — never invent a query).
 */
export function domainSearchCoverage(
  subjects?: readonly string[] | null,
): {
  subjects: string[];
  has_default: boolean;
  default_query: string;
  covered: string[];
  uncovered: string[];
} {
  const list = (subjects || [])
    .map((s) => String(s || "").trim().toLowerCase())
    .filter(Boolean);
  const default_query = domainAwareSearchDefault(list);
  const has_default = Boolean(default_query);
  // Subjects that participate in a match when has_default (heuristic: any subject
  // that alone produces a non-empty default is covered; others are co-tags).
  const covered: string[] = [];
  const uncovered: string[] = [];
  for (const s of list) {
    if (domainAwareSearchDefault([s])) covered.push(s);
    else uncovered.push(s);
  }
  return {
    subjects: list,
    has_default,
    default_query,
    covered,
    uncovered,
  };
}

/**
 * Residual (aod): normalize host subjects for domain-aware deep-research
 * goal_hint (lower-case, dedupe, first-seen). Never invents domains.
 */
export function normalizeDomainSubjects(
  subjects?: readonly string[] | null,
): string[] {
  const domains = (subjects || [])
    .map((s) => String(s || "").trim().toLowerCase())
    .filter(Boolean);
  return [...new Set(domains)];
}

/**
 * Residual (aod): goal_hint clause ` · research_domains=a,b` or empty.
 * Shared by TwinNotes chase (aoc) + HostedHtml float DR (aod).
 */
export function formatResearchDomainsClause(
  subjects?: readonly string[] | null,
): string {
  const unique = normalizeDomainSubjects(subjects);
  return unique.length > 0
    ? ` · research_domains=${unique.join(",")}`
    : "";
}
