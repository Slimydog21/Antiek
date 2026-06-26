/**
 * Reading workflow — condense KB-static ResearchArtifact HTML (ANT-AHT).
 * Mirrors Python `consume_kb_artifact` / `#antiek-artifact-v1` island.
 * Goal harness deliverable 2026-06-26.
 */

export interface ReadingCondensedFinding {
  nodeId: string;
  text: string;
  confidence: string | null;
}

export interface ReadingCondensedGap {
  nodeId: string;
  text: string;
  escalated: boolean;
}

export interface ReadingCondensedView {
  investigationId: string;
  problemQuestion: string;
  contentHash: string;
  findings: ReadingCondensedFinding[];
  openGaps: ReadingCondensedGap[];
  synthesisExcerpt: string | null;
  agentNotes: string[];
  scriptFree: boolean;
}

const JSON_ISLAND_RE =
  /<script\s+type="application\/json"\s+id="antiek-artifact-v1"\s*>([\s\S]*?)<\/script>/i;

const EXECUTABLE_SCRIPT_RE =
  /<script(?![^>]*\btype\s*=\s*['"]application\/json['"])/i;

export function hasExecutableScripts(html: string): boolean {
  return EXECUTABLE_SCRIPT_RE.test(html);
}

export function parseArtifactJsonIsland(html: string): Record<string, unknown> {
  const m = JSON_ISLAND_RE.exec(html);
  if (!m) {
    throw new Error("missing #antiek-artifact-v1 JSON block");
  }
  return JSON.parse(m[1].trim()) as Record<string, unknown>;
}

export function condenseKbArtifactHtml(html: string): ReadingCondensedView {
  if (hasExecutableScripts(html)) {
    throw new Error("KB artifact must be script-free for reading consumption");
  }
  const data = parseArtifactJsonIsland(html);
  const insights = (data.insights as Array<Record<string, unknown>>) ?? [];
  const questions = (data.open_questions as Array<Record<string, unknown>>) ?? [];
  const notes = (data.agent_notes as string[]) ?? [];
  return {
    investigationId: String(data.investigation_id ?? ""),
    problemQuestion: String(data.problem_question ?? ""),
    contentHash: typeof data.content_hash === "string"
      ? data.content_hash
      : "",
    findings: insights.map((ins) => ({
      nodeId: String(ins.node_id ?? ""),
      text: String(ins.text ?? ""),
      confidence: ins.confidence != null ? String(ins.confidence) : null,
    })),
    openGaps: questions.map((q) => ({
      nodeId: String(q.node_id ?? ""),
      text: String(q.text ?? ""),
      escalated: Boolean(q.escalated),
    })),
    synthesisExcerpt:
      data.synthesis_excerpt != null ? String(data.synthesis_excerpt) : null,
    agentNotes: notes.filter((n) => (n ?? "").trim().length > 0),
    scriptFree: true,
  };
}