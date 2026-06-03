import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

/**
 * verify_handoff — ANT-EXEC-H2V SPR-03 handoff schema linter.
 *
 * Parses a markdown Handoff Packet (see docs/agent-execution/TEMPLATES.md) and
 * fails closed on briefing theater the adversarial rubric names:
 *   R-01  Env Card present
 *   R-03  pytest|tail not the sole verify sign-off
 *   R-04  Gate results table non-empty with commands
 *   R-06  ### Not proved before ### Status
 *   R-20  Required template headings present (or N/A — reason)
 *
 * USAGE
 *   npx tsx tools/agent/verify_handoff.ts <handoff.md>
 *   echo "$HANDOFF" | npx tsx tools/agent/verify_handoff.ts -
 */

export type VerifyIssueCode =
  | "missing_heading"
  | "empty_section"
  | "not_proved_after_status"
  | "empty_gate_table"
  | "pytest_tail_theater";

export interface VerifyIssue {
  code: VerifyIssueCode;
  message: string;
  heading?: string;
}

export interface VerifyResult {
  ok: boolean;
  issues: VerifyIssue[];
}

/** Minimum handoff headings per TEMPLATES.md "Heading index (≥8 required ###)". */
export const REQUIRED_HEADINGS: readonly string[] = [
  "### Env Card",
  "### Not proved",
  "### Status",
  "### Files touched",
  "### Milestones (checkboxes)",
  "### Gate results",
  "### Steelman rejected alternative",
  "### Open questions",
] as const;

/** pytest piped to tail as the only recorded verify command (R-03 / T-01). */
const PYTEST_TAIL_THEATER =
  /pytest\b[^|\n]*\|\s*tail\b/i;

const NA_REASON = /^N\/A\s*[—–-]\s*.+/is;

export interface HandoffSection {
  heading: string;
  body: string;
  startLine: number;
}

/** Split markdown on level-3 headings (### …). */
export function parseHandoffSections(markdown: string): HandoffSection[] {
  const lines = markdown.replace(/\r\n/g, "\n").split("\n");
  const sections: HandoffSection[] = [];
  let current: HandoffSection | null = null;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]!;
    const m = line.match(/^(###\s+.+)$/);
    if (m) {
      if (current) sections.push(current);
      current = { heading: m[1]!.trimEnd(), body: "", startLine: i + 1 };
      continue;
    }
    if (current) {
      current.body += (current.body ? "\n" : "") + line;
    }
  }
  if (current) sections.push(current);
  return sections;
}

export function sectionByHeading(
  sections: HandoffSection[],
  heading: string,
): HandoffSection | undefined {
  return sections.find((s) => s.heading === heading);
}

/** Section is filled when it has prose or an explicit N/A — reason waiver. */
export function sectionHasContent(body: string): boolean {
  const trimmed = body.trim();
  if (!trimmed) return false;
  if (NA_REASON.test(trimmed)) return true;
  return trimmed.length > 0;
}

export interface GateRow {
  gate: string;
  command: string;
  exit: string;
  logPath: string;
}

/** Split a markdown table row on | while ignoring pipes inside \`backticks\`. */
export function splitTableRow(line: string): string[] {
  const trimmed = line.trim();
  if (!trimmed.startsWith("|")) return [];
  const inner = trimmed.slice(1, trimmed.endsWith("|") ? -1 : undefined);
  const cells: string[] = [];
  let cell = "";
  let inTicks = false;
  for (let i = 0; i < inner.length; i++) {
    const ch = inner[i]!;
    if (ch === "`") {
      inTicks = !inTicks;
      cell += ch;
      continue;
    }
    if (ch === "|" && !inTicks) {
      cells.push(cell.trim());
      cell = "";
      continue;
    }
    cell += ch;
  }
  cells.push(cell.trim());
  return cells;
}

/** Parse the | gate | command | exit | log path | table under ### Gate results. */
export function parseGateResultsTable(body: string): GateRow[] {
  const lines = body.split("\n");
  let headerIdx = -1;
  for (let i = 0; i < lines.length; i++) {
    const lower = lines[i]!.toLowerCase();
    if (
      lower.includes("gate") &&
      lower.includes("command") &&
      lower.includes("|")
    ) {
      headerIdx = i;
      break;
    }
  }
  if (headerIdx < 0) return [];

  const rows: GateRow[] = [];
  for (let i = headerIdx + 1; i < lines.length; i++) {
    const line = lines[i]!.trim();
    if (!line.startsWith("|")) break;
    if (/^\|[\s\-:|]+\|$/.test(line.replace(/\s/g, ""))) continue;

    const cells = splitTableRow(line);
    if (cells.length < 3) continue;

    const [gate, command, exit, logPath = ""] = cells;
    if (!gate && !command) continue;
    if (/^gate$/i.test(gate) && /^command$/i.test(command)) continue;

    rows.push({
      gate: gate ?? "",
      command: command ?? "",
      exit: exit ?? "",
      logPath: logPath ?? "",
    });
  }
  return rows;
}

function isNaGateCommand(command: string): boolean {
  return /^N\/A\s*[—–-]/i.test(command.trim());
}

function normalizeGateCommand(command: string): string {
  return command.trim().replace(/^`+|`+$/g, "");
}

/** True when every non-waived gate command is pytest|tail theater (R-03). */
export function isPytestTailSoleVerify(rows: GateRow[]): boolean {
  const commands = rows
    .map((r) => normalizeGateCommand(r.command))
    .filter((c) => c.length > 0 && !isNaGateCommand(c));
  if (commands.length === 0) return false;
  return commands.every((c) => PYTEST_TAIL_THEATER.test(c));
}

function headingOrder(sections: HandoffSection[], heading: string): number {
  const idx = sections.findIndex((s) => s.heading === heading);
  return idx < 0 ? Number.POSITIVE_INFINITY : idx;
}

/** Core linter — pure, no I/O. */
export function verifyHandoff(markdown: string): VerifyResult {
  const issues: VerifyIssue[] = [];
  const sections = parseHandoffSections(markdown);

  for (const heading of REQUIRED_HEADINGS) {
    const section = sectionByHeading(sections, heading);
    if (!section) {
      issues.push({
        code: "missing_heading",
        heading,
        message: `Missing required heading: ${heading}`,
      });
      continue;
    }
    if (!sectionHasContent(section.body)) {
      issues.push({
        code: "empty_section",
        heading,
        message: `${heading} is empty; add content or "N/A — <reason>"`,
      });
    }
  }

  const notProvedIdx = headingOrder(sections, "### Not proved");
  const statusIdx = headingOrder(sections, "### Status");
  if (
    notProvedIdx !== Number.POSITIVE_INFINITY &&
    statusIdx !== Number.POSITIVE_INFINITY &&
    notProvedIdx > statusIdx
  ) {
    issues.push({
      code: "not_proved_after_status",
      message: "### Not proved must appear before ### Status (R-06)",
    });
  }

  const gateSection = sectionByHeading(sections, "### Gate results");
  if (gateSection) {
    const rows = parseGateResultsTable(gateSection.body);
    if (rows.length === 0) {
      issues.push({
        code: "empty_gate_table",
        heading: "### Gate results",
        message:
          "### Gate results needs a gate table with ≥1 data row (command + exit + log path)",
      });
    } else if (isPytestTailSoleVerify(rows)) {
      issues.push({
        code: "pytest_tail_theater",
        heading: "### Gate results",
        message:
          "Gate verify cannot be sole pytest|tail; retain full log path or paste (R-03)",
      });
    }
  }

  return { ok: issues.length === 0, issues };
}

function formatIssues(issues: VerifyIssue[]): string {
  return issues.map((i) => `- [${i.code}] ${i.message}`).join("\n");
}

/** CLI entry when executed via tsx. */
export function main(argv: string[] = process.argv.slice(2)): number {
  const path = argv[0];
  if (!path) {
    console.error("Usage: verify_handoff.ts <handoff.md|-");
    return 2;
  }

  const markdown =
    path === "-"
      ? readFileSync(0, "utf8")
      : readFileSync(path, "utf8");

  const result = verifyHandoff(markdown);
  if (result.ok) {
    console.log("HANDOFF_OK");
    return 0;
  }
  console.error("HANDOFF_FAIL\n" + formatIssues(result.issues));
  return 1;
}

const isDirect = process.argv[1] === fileURLToPath(import.meta.url);
if (isDirect) {
  process.exit(main());
}