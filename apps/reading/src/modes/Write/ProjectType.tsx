import { useState } from "react";

import type { DeliverableKind } from "../../lib/api";
import { emitWernerExperience } from "../../werner/reactionBus";

/**
 * ProjectType — open-ended project type, presets SEED (do not GATE) (SPR-09 M4).
 *
 * "Project-type is OPEN-ENDED text the AI interprets ('research memo / chapter /
 * biography section' are presets that SEED, not a hardcoded dropdown that
 * GATES)." The writer can type ANYTHING ("a wedding toast", "a grant rebuttal");
 * the presets are one-tap seeds, not the only allowed values.
 *
 * The substrate's `deliverable_kind` is a closed enum (research_memo,
 * book_chapter, biography_section, investor_brief, general_essay) — it steers
 * the creative_writer prompt's register. We map the freeform type to its
 * closest preset kind for that steer, and a NOVEL type the AI has never seen
 * falls to `general_essay` — the OPEN default, NOT a hidden hardcoded shape:
 * general_essay imposes no fixed section skeleton, so the inferred outline does
 * not crash or snap to a memo/chapter template (rigor #3d). The freeform label
 * itself is preserved as the piece's working type so the AI interprets the
 * writer's actual intent, not just the bucket.
 */

/** Presets that SEED a kind. Each maps a friendly label → the backend kind
 * whose register best fits. These are suggestions, not the allowed set. */
export const PROJECT_TYPE_PRESETS: ReadonlyArray<{
  label: string;
  kind: DeliverableKind;
}> = [
  { label: "Research memo", kind: "research_memo" },
  { label: "Book chapter", kind: "book_chapter" },
  { label: "Biography section", kind: "biography_section" },
  { label: "Investor brief", kind: "investor_brief" },
  { label: "Essay", kind: "general_essay" },
];

/** Resolve a freeform type label → a backend kind for the prompt's register.
 * A preset (case-insensitive) maps to its kind; ANYTHING else falls to
 * general_essay — the open default that imposes no fixed outline shape, so a
 * type the AI has never seen never gates or crashes (presets seed, not gate). */
export function resolveKind(freeform: string): DeliverableKind {
  const t = freeform.trim().toLowerCase();
  const preset = PROJECT_TYPE_PRESETS.find((p) => p.label.toLowerCase() === t);
  if (preset) return preset.kind;
  // Loose keyword seeding for near-matches (still non-gating — unmatched text
  // is fine, it just lands on general_essay).
  if (t.includes("memo")) return "research_memo";
  if (t.includes("chapter")) return "book_chapter";
  if (t.includes("biograph")) return "biography_section";
  if (t.includes("brief") || t.includes("investor")) return "investor_brief";
  return "general_essay";
}

export interface ProjectTypeValue {
  /** The freeform label the writer typed (what the AI interprets). */
  freeform: string;
  /** The backend kind it resolved to (the prompt register). */
  kind: DeliverableKind;
}

export interface ProjectTypeFieldProps {
  value: ProjectTypeValue;
  onChange: (next: ProjectTypeValue) => void;
  disabled?: boolean;
}

export function ProjectTypeField({ value, onChange, disabled }: ProjectTypeFieldProps) {
  const [text, setText] = useState(value.freeform);

  function commit(freeform: string) {
    setText(freeform);
    onChange({ freeform, kind: resolveKind(freeform) });
  }

  return (
    <div data-testid="project-type" className="space-y-1">
      <input
        value={text}
        onChange={(e) => commit(e.target.value)}
        disabled={disabled}
        placeholder="What kind of piece? (anything — memo, chapter, toast, rebuttal…)"
        className="w-full rounded border border-rule px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-sun dark:border-charcoal-1"
      />
      <div className="flex flex-wrap gap-1">
        {PROJECT_TYPE_PRESETS.map((p) => (
          <button
            key={p.kind}
            type="button"
            disabled={disabled}
            onClick={() => { emitWernerExperience("highlight"); commit(p.label) }}
            className={
              "rounded-full border px-2 py-0.5 text-[11px] disabled:opacity-60 " +
              (resolveKind(text) === p.kind && text.trim()
                ? "border-ocean bg-ocean/15 text-ocean"
                : "border-rule text-ink-soft hover:border-ocean dark:border-charcoal-1")
            }
          >
            {p.label}
          </button>
        ))}
      </div>
    </div>
  );
}

export default ProjectTypeField;
