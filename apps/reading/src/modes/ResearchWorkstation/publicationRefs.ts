/**
 * Publication references for deep research launch (residual cj).
 *
 * Operators attach arxiv / substack / URL handles that ground a research
 * prompt. Hydration reuses shipped engagement hydrate-ref (offline identity
 * by default; live only with env injectors). HTML-first assets only.
 */

import {
  hydratePublicationRef,
  type HydrateRefResponse,
} from "../../api/engagement";

/** Parse one ref per non-empty line (arxiv:…, substack:…, https://…). */
export function parsePublicationRefs(raw: string): string[] {
  return (raw || "")
    .split(/\r?\n+/)
    .map((line) => line.trim())
    .filter((line) => line.length > 0);
}

/**
 * Append a grounded references block to the research question so Hermes /
 * note-taker see the handles. Does not invent paper abstracts.
 */
export function questionWithPublicationRefs(
  question: string,
  refs: string[],
): string {
  const q = (question || "").trim();
  if (!refs.length) return q;
  const block = refs.map((r) => `- ${r}`).join("\n");
  return `${q}\n\nPublication references to ground this research:\n${block}`;
}

export type HydrateRefsResult = {
  ok: HydrateRefResponse[];
  failed: Array<{ reference: string; error: string }>;
  view_format: "html";
};

/** Hydrate each ref via engagement API (offline-safe by default). */
export async function hydratePublicationRefs(
  refs: string[],
): Promise<HydrateRefsResult> {
  const ok: HydrateRefResponse[] = [];
  const failed: Array<{ reference: string; error: string }> = [];
  for (const reference of refs) {
    try {
      const asset = await hydratePublicationRef({
        reference,
        include_html: true,
      });
      if (asset.view_format !== "html") {
        failed.push({
          reference,
          error: `view_format must be html (got ${asset.view_format})`,
        });
        continue;
      }
      ok.push(asset);
    } catch (e) {
      failed.push({
        reference,
        error: e instanceof Error ? e.message : String(e),
      });
    }
  }
  return { ok, failed, view_format: "html" };
}
