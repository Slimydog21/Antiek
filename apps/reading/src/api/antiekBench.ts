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

const BENCH_TASKS = new Set<BenchTask>([
  "deep_research",
  "research_synthesis",
  "reading",
  "twin_note",
  "writing",
  "multimedia",
  "general",
]);
const WEEK_ID = /^\d{4}-W(?:0[1-9]|[1-4]\d|5[0-3])$/;

function validBoundedString(value: unknown, maxLength: number): value is string {
  return typeof value === "string" && value.length >= 1 && value.length <= maxLength;
}

function validGeneratedAt(value: unknown): value is string {
  return (
    typeof value === "string" &&
    /(?:Z|[+-]\d{2}:\d{2})$/.test(value) &&
    Number.isFinite(Date.parse(value))
  );
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
    if (typeof row.task !== "string" || !BENCH_TASKS.has(row.task as BenchTask)) {
      throw new Error(`measurement ${index}.task is invalid`);
    }
    for (const [key, ceiling] of [
      ["tier", 64],
      ["provider", 128],
      ["model", 256],
    ] as const) {
      if (!validBoundedString(row[key], ceiling)) {
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
      row.samples < 1 ||
      row.samples > 1_000_000
    ) {
      throw new Error(`measurement ${index}.samples is invalid`);
    }
    return row as unknown as BenchMeasurement;
  });
  if (!value.notes.every((note) => typeof note === "string")) {
    throw new Error("benchmark notes must be strings");
  }
  if (value.status === "unavailable") {
    if (
      measurements.length !== 0 ||
      value.week_id !== null ||
      value.generated_at !== null
    ) {
      throw new Error("unavailable benchmark cannot contain measured evidence");
    }
  } else if (
    measurements.length === 0 ||
    typeof value.week_id !== "string" ||
    !WEEK_ID.test(value.week_id) ||
    !validGeneratedAt(value.generated_at)
  ) {
    throw new Error("measured benchmark metadata is invalid");
  }
  return {
    authority: "advisory",
    status: value.status,
    week_id: value.week_id as string | null,
    generated_at: value.generated_at as string | null,
    measurements,
    notes: value.notes as string[],
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
