import type {
  MultimediaPlanWire,
  MultimediaScriptLineWire,
  MultimediaSourceCitationWire,
} from "../../api/multimedia";

export type ProjectedChapter = {
  id: string;
  title: string;
  minutes: number;
  purpose: string;
  visualLabel: "planned" | "sourced" | "diagram";
  sourceId: string | null;
  transcript: string;
  scenePurpose: string | null;
};

export type ProjectedSource = {
  id: string;
  title: string;
  status: "cited";
  detail: string;
};

export type MultimediaPlanProjection = {
  suggestions: string[];
  coverageOptions: Array<{ id: string; title: string; teaches: string; tradeoff: string; evidenceCount: number }>;
  chosenArcIds: string[];
  depth: "overview" | "intermediate" | "deep";
  sourceScope: string | null;
  omissions: string[];
  chapters: ProjectedChapter[];
  sources: ProjectedSource[];
  unsourcedClaims: string[];
};

export type PlanProjectionResult =
  | { ok: true; value: MultimediaPlanProjection }
  | { ok: false; error: string };

export function projectMultimediaPlan(input: unknown): PlanProjectionResult {
  if (!input || typeof input !== "object") return invalid("Persisted plan is unavailable.");
  const plan = input as MultimediaPlanWire;
  if (!Array.isArray(plan.chapters) || !Array.isArray(plan.script_lines)) {
    return invalid("Plan chapters or script are unavailable.");
  }
  if (!Array.isArray(plan.suggestions) || !Array.isArray(plan.scenes) || !Array.isArray(plan.omissions)) {
    return invalid("Plan review fields are unavailable.");
  }
  if (!Array.isArray(plan.unsourced_line_ids) || plan.chapters.length === 0) {
    return invalid("Plan grounding state is unavailable.");
  }
  if (!plan.request) {
    return invalid("Plan depth is unavailable.");
  }
  const depth = plan.request.depth ?? "intermediate";
  if (!["overview", "intermediate", "deep"].includes(depth)) {
    return invalid("Plan depth is unavailable.");
  }
  if (
    plan.request.source_scope !== undefined &&
    plan.request.source_scope !== null &&
    typeof plan.request.source_scope !== "string"
  ) {
    return invalid("Plan research scope is unavailable.");
  }
  if (
    !Array.isArray(plan.chosen_arc_ids) ||
    plan.chosen_arc_ids.some((id) => typeof id !== "string" || !id) ||
    new Set(plan.chosen_arc_ids).size !== plan.chosen_arc_ids.length
  ) {
    return invalid("Plan coverage selection conflicts.");
  }
  if (
    plan.suggestions.some(
      (item) =>
        !item ||
        typeof item.title !== "string" ||
        typeof item.teaches !== "string" ||
        typeof item.tradeoff !== "string" ||
        typeof item.arc_id !== "string" ||
        !item.arc_id ||
        !Array.isArray(item.evidence) ||
        item.evidence.some((citation) => !validCitation(citation)),
    ) ||
    plan.omissions.some((item) => typeof item !== "string") ||
    new Set(plan.unsourced_line_ids).size !== plan.unsourced_line_ids.length
  ) {
    return invalid("Plan review text or grounding identity conflicts.");
  }
  const suggestionArcIds = plan.suggestions.map((item) => item.arc_id);
  if (
    new Set(suggestionArcIds).size !== suggestionArcIds.length ||
    plan.chosen_arc_ids.some((id) => !suggestionArcIds.includes(id))
  ) {
    return invalid("Plan coverage selection conflicts.");
  }

  const lines = new Map<string, MultimediaScriptLineWire>();
  const citations = new Map<string, MultimediaSourceCitationWire>();
  for (const line of plan.script_lines) {
    if (!validLine(line) || lines.has(line.line_id)) return invalid("Plan script identity conflicts.");
    lines.set(line.line_id, line);
    for (const citation of line.citations) {
      if (!validCitation(citation)) return invalid("Plan citation identity conflicts.");
      const existing = citations.get(citation.chunk_id);
      if (existing && existing.document_id !== citation.document_id) {
        return invalid("Plan citation identity conflicts.");
      }
      citations.set(citation.chunk_id, citation);
    }
  }

  const scenesByChapter = new Map<string, MultimediaPlanWire["scenes"][number][]>();
  const sceneIds = new Set<string>();
  for (const scene of plan.scenes) {
    if (
      !scene || typeof scene.scene_id !== "string" || !scene.scene_id || sceneIds.has(scene.scene_id) ||
      typeof scene.chapter_id !== "string" || !scene.chapter_id || typeof scene.visual_intent !== "string" ||
      typeof scene.information_purpose !== "string" || !Array.isArray(scene.narration_line_ids) ||
      !Array.isArray(scene.source_chunk_ids) || scene.narration_line_ids.some((id) => typeof id !== "string" || !lines.has(id)) ||
      scene.source_chunk_ids.some((id) => typeof id !== "string" || !id)
    ) {
      return invalid("Storyboard scene identity conflicts.");
    }
    if (scene.narration_line_ids.some((id) => !id.startsWith(`${scene.chapter_id}-line-`))) {
      return invalid("Storyboard narration provenance conflicts.");
    }
    sceneIds.add(scene.scene_id);
    const values = scenesByChapter.get(scene.chapter_id) ?? [];
    values.push(scene);
    scenesByChapter.set(scene.chapter_id, values);
  }

  const chapters: ProjectedChapter[] = [];
  const chapterIds = new Set<string>();
  for (const chapter of plan.chapters) {
    if (
      !chapter ||
      typeof chapter.chapter_id !== "string" ||
      !chapter.chapter_id ||
      chapterIds.has(chapter.chapter_id) ||
      typeof chapter.title !== "string" ||
      typeof chapter.purpose !== "string" ||
      typeof chapter.minutes !== "number" ||
      !Number.isFinite(chapter.minutes) ||
      !Array.isArray(chapter.source_chunk_ids)
    ) {
      return invalid("Plan chapter identity conflicts.");
    }
    if (chapter.source_chunk_ids.some((id) => typeof id !== "string" || !id)) {
      return invalid("Plan chapter source identity conflicts.");
    }
    chapterIds.add(chapter.chapter_id);
    const chapterLines = [...lines.values()]
      .filter((line) => line.line_id.startsWith(`${chapter.chapter_id}-line-`))
      .sort((a, b) => a.sequence - b.sequence);
    if (chapterLines.length === 0) return invalid(`Chapter ${chapter.chapter_id} has no script.`);
    const scenes = scenesByChapter.get(chapter.chapter_id) ?? [];
    const visualIntent = scenes.map((scene) => scene.visual_intent).join(" ").toLowerCase();
    const chapterCitationIds = new Set(chapterLines.flatMap((line) => line.citations.map((citation) => citation.chunk_id)));
    const sourceId = chapter.source_chunk_ids.find((id) => chapterCitationIds.has(id)) ?? null;
    chapters.push({
      id: chapter.chapter_id,
      title: chapter.title,
      minutes: chapter.minutes,
      purpose: chapter.purpose,
      visualLabel: visualIntent.includes("diagram")
        ? "diagram"
        : sourceId
          ? "sourced"
          : "planned",
      sourceId,
      transcript: chapterLines.map((line) => line.text).join("\n\n"),
      scenePurpose: scenes[0]?.information_purpose ?? null,
    });
  }
  if ([...scenesByChapter.keys()].some((id) => !chapterIds.has(id))) {
    return invalid("Storyboard references an unavailable chapter.");
  }
  const sourceIdsByChapter = new Map(plan.chapters.map((chapter) => [chapter.chapter_id, new Set(chapter.source_chunk_ids)]));
  if (plan.scenes.some((scene) => scene.source_chunk_ids.some((id) => !sourceIdsByChapter.get(scene.chapter_id)?.has(id)))) {
    return invalid("Storyboard source provenance conflicts.");
  }

  const actualUnsourcedLineIds = [...lines.values()]
    .filter((line) => line.kind === "factual" && line.citations.length === 0)
    .map((line) => line.line_id)
    .sort();
  const recordedUnsourcedLineIds = [...plan.unsourced_line_ids].sort();
  if (
    actualUnsourcedLineIds.length !== recordedUnsourcedLineIds.length ||
    actualUnsourcedLineIds.some((lineId, index) => lineId !== recordedUnsourcedLineIds[index])
  ) {
    return invalid("Unsourced claim ledger conflicts.");
  }
  const unsourcedClaims = plan.unsourced_line_ids.map((lineId) => {
    const line = lines.get(lineId);
    if (!line || line.kind !== "factual" || line.citations.length > 0 || !line.unsourced_reason) {
      return "";
    }
    return `${line.text} — ${line.unsourced_reason}`;
  });
  if (unsourcedClaims.some((claim) => !claim)) return invalid("Unsourced claim ledger conflicts.");

  const sources = [...citations.values()].map((citation) => ({
    id: citation.chunk_id,
    title: citation.document_id,
    status: "cited" as const,
    detail: citation.locator || "Source reference",
  }));
  return {
    ok: true,
    value: {
      suggestions: plan.suggestions.map((item) => `${item.title}: ${item.teaches} ${item.tradeoff}`),
      coverageOptions: plan.suggestions.map((item) => ({
        id: item.arc_id,
        title: item.title,
        teaches: item.teaches,
        tradeoff: item.tradeoff,
        evidenceCount: Array.isArray(item.evidence) ? item.evidence.length : 0,
      })),
      chosenArcIds: plan.chosen_arc_ids,
      depth,
      sourceScope: plan.request.source_scope ?? null,
      omissions: plan.omissions,
      chapters,
      sources,
      unsourcedClaims,
    },
  };
}

function validLine(line: MultimediaScriptLineWire): boolean {
  const kinds = new Set(["factual", "transition", "narration", "opinion", "instruction"]);
  return Boolean(
    line &&
      typeof line.line_id === "string" &&
      line.line_id &&
      typeof line.sequence === "number" &&
      typeof line.text === "string" &&
      line.text &&
      kinds.has(line.kind) &&
      Array.isArray(line.citations),
  );
}

function validCitation(citation: MultimediaSourceCitationWire): boolean {
  return Boolean(
    citation &&
      typeof citation.chunk_id === "string" &&
      citation.chunk_id &&
      typeof citation.document_id === "string" &&
      citation.document_id,
  );
}

function invalid(error: string): PlanProjectionResult {
  return { ok: false, error };
}
