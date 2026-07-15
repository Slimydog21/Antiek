/**
 * Recursive twin note-taker — pure document model (reading UI).
 *
 * Operator vision: every information asset has an LLM-authored twin of
 * insights + questions. This module is the hard-to-vary pure shape the UI
 * renders; generation/automation stays behind the merge wall
 * (twin-recursion-automation-seam-spec).
 *
 * Anti-recursion: twins are non-twinnable (`isTwin: true`).
 */

export type TwinInsight = {
  id: string;
  text: string;
  /** Optional provenance pointer into the source asset. */
  sourceSpan?: string;
};

export type TwinQuestion = {
  id: string;
  text: string;
  open: boolean;
};

export type TwinDocument = {
  id: string;
  /** Parent information asset id. */
  parentAssetId: string;
  insights: TwinInsight[];
  questions: TwinQuestion[];
  /** Content hash of the source when twin was proposed (staleness later). */
  sourceContentHash?: string;
  authority: "advisory";
  /** Always true — twins never spawn twins. */
  isTwin: true;
  /** Generation status for UI honesty. */
  status: "empty" | "pending" | "ready" | "stale" | "error";
  errorReason?: string;
};

export function emptyTwin(parentAssetId: string, id: string): TwinDocument {
  return {
    id,
    parentAssetId,
    insights: [],
    questions: [],
    authority: "advisory",
    isTwin: true,
    status: "empty",
  };
}

export function isTwinnableAsset(meta: {
  isTwin?: boolean;
  twinOf?: string | null;
}): boolean {
  if (meta.isTwin) return false;
  if (meta.twinOf) return false;
  return true;
}

/**
 * Pure merge of two twin documents for the same parent (advisory combine).
 * Does not write; operator uses this for multi-context leverage.
 */
export function mergeTwinDocuments(
  a: TwinDocument,
  b: TwinDocument,
): TwinDocument | { ok: false; reason: "parent_mismatch" | "not_twins" } {
  if (!a.isTwin || !b.isTwin) return { ok: false, reason: "not_twins" };
  if (a.parentAssetId !== b.parentAssetId) {
    return { ok: false, reason: "parent_mismatch" };
  }
  const insightKey = new Set(a.insights.map((i) => i.text.trim().toLowerCase()));
  const questionKey = new Set(
    a.questions.map((q) => q.text.trim().toLowerCase()),
  );
  const insights = [
    ...a.insights,
    ...b.insights.filter(
      (i) => !insightKey.has(i.text.trim().toLowerCase()),
    ),
  ];
  const questions = [
    ...a.questions,
    ...b.questions.filter(
      (q) => !questionKey.has(q.text.trim().toLowerCase()),
    ),
  ];
  return {
    id: `merged:${a.id}:${b.id}`,
    parentAssetId: a.parentAssetId,
    insights,
    questions,
    sourceContentHash: a.sourceContentHash ?? b.sourceContentHash,
    authority: "advisory",
    isTwin: true,
    status: "ready",
  };
}

/** Demo / offline fixture for the panel when no twin API is live. */
export function demoTwinForAsset(parentAssetId: string): TwinDocument {
  return {
    id: `twin:demo:${parentAssetId}`,
    parentAssetId,
    insights: [
      {
        id: "i1",
        text: "The asset argues that recursive substrate compounds search quality.",
      },
      {
        id: "i2",
        text: "HTML-native delivery is treated as a control surface for agents.",
      },
    ],
    questions: [
      {
        id: "q1",
        text: "What evidence would falsify the universality of twin coverage?",
        open: true,
      },
      {
        id: "q2",
        text: "How should budget gates allocate twin-generation vs research spend?",
        open: true,
      },
    ],
    authority: "advisory",
    isTwin: true,
    status: "ready",
  };
}
