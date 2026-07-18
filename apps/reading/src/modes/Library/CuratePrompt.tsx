import { useState } from "react";

import { LemonButton, LemonInput } from "../../components/lemon";
import { emitWernerExperience } from "../../werner/reactionBus";

/**
 * Prompt-to-curate input (Read SPR-04). The reader describes what they
 * want to read ("stoicism for someone burned out") and the shelf
 * re-ranks to a curated reading list. Curation runs only over servable
 * books (the backend enforces it), so the prompt can never surface a
 * title you can't actually read.
 */

export interface CuratePromptProps {
  onCurate: (prompt: string) => void;
  onClear: () => void;
  active: boolean;
  busy?: boolean;
}

export default function CuratePrompt({ onCurate, onClear, active, busy }: CuratePromptProps) {
  const [value, setValue] = useState("");

  const submit = () => {
    const p = value.trim();
    if (!p) return;
    // Living-TV: prompt-to-curate is a curious highlight glance.
    emitWernerExperience("highlight");
    onCurate(p);
  };

  return (
    <form
      className="flex items-center gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
    >
      <LemonInput
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder="Curate the shelf — e.g. “stoicism for burnout”"
        aria-label="Curate the library by prompt"
        className="flex-1"
      />
      <LemonButton type="submit" variant="primary" size="sm" disabled={busy || !value.trim()}>
        {busy ? "Curating…" : "Curate"}
      </LemonButton>
      {active && (
        <LemonButton
          type="button"
          variant="tertiary"
          size="sm"
          onClick={() => {
            setValue("");
            onClear();
          }}
        >
          Clear
        </LemonButton>
      )}
    </form>
  );
}
