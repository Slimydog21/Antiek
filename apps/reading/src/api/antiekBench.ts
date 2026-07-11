/**
 * Antiek-bench weekly presentation client (advisory Settings view).
 *
 * POST /settings/antiek-bench/weekly — inject records; does not run the bench.
 */

import { API_BASE, apiFetch } from "../lib/api";

export interface BenchScoreRow {
  task: string;
  model_id: string;
  score: number | null;
  n_runs: number;
  notes: string;
}

export interface WeeklyBenchViewResponse {
  week_id: string;
  authority: string;
  best_by_task: Record<string, string>;
  incomplete: boolean;
  notes: string[];
  scores: BenchScoreRow[];
}

export interface WeeklyBenchRequest {
  week_id?: string;
  records?: Array<{
    task?: string;
    model_id: string;
    score?: number | null;
    n_runs?: number;
    notes?: string;
  }>;
}

async function readJson<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`antiek-bench API ${res.status}: ${text.slice(0, 200)}`);
  }
  return (await res.json()) as T;
}

export async function fetchWeeklyBenchView(
  req: WeeklyBenchRequest,
): Promise<WeeklyBenchViewResponse> {
  const res = await apiFetch(`${API_BASE}/settings/antiek-bench/weekly`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      week_id: req.week_id ?? "",
      records: req.records ?? [],
    }),
  });
  return readJson<WeeklyBenchViewResponse>(res);
}

export function formatScore(score: number | null | undefined): string {
  if (score === null || score === undefined) return "NOT MEASURED";
  return score.toFixed(3);
}

export function formatBestModel(modelId: string | undefined): string {
  if (!modelId) return "none";
  return modelId;
}
