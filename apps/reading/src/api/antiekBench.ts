import { API_BASE, apiFetch } from "../lib/api";

export type BenchTask =
  | "deep_research"
  | "research_synthesis"
  | "reading"
  | "twin_note"
  | "writing"
  | "multimedia"
  | "general";

export interface BenchMeasurement {
  task: BenchTask;
  tier: string;
  provider: string;
  model: string;
  score: number;
  samples: number;
}

export interface WeeklyBenchViewResponse {
  authority: "advisory";
  status: "measured" | "unavailable";
  week_id: string | null;
  generated_at: string | null;
  measurements: BenchMeasurement[];
  notes: string[];
}

export class AntiekBenchHttpError extends Error {
  constructor(
    readonly status: number,
    readonly body: string,
  ) {
    super(`Antiek-bench API ${status}: ${body.slice(0, 200)}`);
    this.name = "AntiekBenchHttpError";
  }
}

function parseWeeklyBench(raw: unknown): WeeklyBenchViewResponse {
  if (!raw || typeof raw !== "object")
    throw new Error("invalid weekly benchmark response");
  const value = raw as Record<string, unknown>;
  if (value.authority !== "advisory")
    throw new Error("benchmark authority must be advisory");
  if (value.status !== "measured" && value.status !== "unavailable") {
    throw new Error("benchmark status is invalid");
  }
  if (!Array.isArray(value.measurements) || !Array.isArray(value.notes)) {
    throw new Error("benchmark measurements and notes must be arrays");
  }
  const measurements = value.measurements.map((rawRow, index) => {
    if (!rawRow || typeof rawRow !== "object")
      throw new Error(`measurement ${index} is invalid`);
    const row = rawRow as Record<string, unknown>;
    for (const key of ["task", "tier", "provider", "model"] as const) {
      if (typeof row[key] !== "string" || !row[key]) {
        throw new Error(`measurement ${index}.${key} is invalid`);
      }
    }
    if (
      typeof row.score !== "number" ||
      !Number.isFinite(row.score) ||
      row.score < 0 ||
      row.score > 1
    ) {
      throw new Error(`measurement ${index}.score is invalid`);
    }
    if (
      typeof row.samples !== "number" ||
      !Number.isSafeInteger(row.samples) ||
      row.samples < 1
    ) {
      throw new Error(`measurement ${index}.samples is invalid`);
    }
    return row as unknown as BenchMeasurement;
  });
  if (value.status === "unavailable" && measurements.length !== 0) {
    throw new Error("unavailable benchmark cannot contain measurements");
  }
  return {
    authority: "advisory",
    status: value.status,
    week_id: typeof value.week_id === "string" ? value.week_id : null,
    generated_at:
      typeof value.generated_at === "string" ? value.generated_at : null,
    measurements,
    notes: value.notes.map((note) => String(note)),
  };
}

export async function fetchWeeklyBenchView(): Promise<WeeklyBenchViewResponse> {
  const response = await apiFetch(`${API_BASE}/settings/antiek-bench/weekly`);
  if (!response.ok)
    throw new AntiekBenchHttpError(response.status, await response.text());
  return parseWeeklyBench(await response.json());
}

export function formatScore(score: number): string {
  return score.toFixed(3);
}
