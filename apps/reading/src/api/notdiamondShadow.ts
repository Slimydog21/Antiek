/**
 * Pure TS NotDiamond shadow log (mirrors #819).
 * Authority forced "shadow"; kill switch default off; no network.
 */

export interface ShadowRecord {
  enabled: boolean;
  authority: "shadow";
  task: string;
  local_model_id: string;
  nd_recommended_model_id: string | null;
  agreement: boolean | null;
  notes: string[];
}

export class NotDiamondShadowError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "NotDiamondShadowError";
  }
}

export function recordShadowComparison(opts: {
  task?: string;
  local_model_id: string;
  nd_recommended_model_id?: string | null;
  enabled?: boolean;
  extra_notes?: string[];
}): ShadowRecord {
  const task = (opts.task || "").trim() || "general";
  const local = (opts.local_model_id || "").trim();
  if (!local) {
    throw new NotDiamondShadowError("local_model_id must be non-empty");
  }

  if (opts.enabled !== true) {
    return {
      enabled: false,
      authority: "shadow",
      task,
      local_model_id: local,
      nd_recommended_model_id: null,
      agreement: null,
      notes: [
        "kill_switch=off — NotDiamond shadow disabled by default",
        "authority=shadow — never production dispatch",
        "no ND recommendation recorded while disabled",
      ],
    };
  }

  let nd =
    opts.nd_recommended_model_id === undefined ||
    opts.nd_recommended_model_id === null
      ? null
      : String(opts.nd_recommended_model_id).trim();
  if (nd === "") nd = null;

  let agreement: boolean | null;
  let notes: string[];
  if (nd === null) {
    agreement = null;
    notes = [
      "kill_switch=on but nd_recommended_model_id missing — agreement unknown",
      "authority=shadow — never production dispatch",
    ];
  } else {
    agreement = nd === local;
    notes = [
      "kill_switch=on — shadow comparison recorded",
      "authority=shadow — never production dispatch",
      agreement ? "agreement=true" : "agreement=false",
    ];
  }
  if (opts.extra_notes) {
    notes.push(...opts.extra_notes.filter((n) => String(n).trim()));
  }

  return {
    enabled: true,
    authority: "shadow",
    task,
    local_model_id: local,
    nd_recommended_model_id: nd,
    agreement,
    notes,
  };
}

export function assertNotProductionAuthority(record: {
  authority?: string;
}): void {
  if (record.authority !== "shadow") {
    throw new NotDiamondShadowError(
      `NotDiamond shadow authority must be 'shadow', got ${JSON.stringify(record.authority)}`,
    );
  }
}
