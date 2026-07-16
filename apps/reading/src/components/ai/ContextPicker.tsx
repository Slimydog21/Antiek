import { useState } from "react";

import { emitWernerExperience } from "../../werner/reactionBus";

import {
  ApiError,
  composeContext,
  type ComposeContextResponse,
  type ContextItem,
  type ContextItemKind,
} from "../../lib/api";

export interface ContextPickerProps {
  /** Called with the composed §9.0-aware system_context after a successful
   * compose, so chat / agent / edit can ground on it. */
  onContextChange: (systemContext: string) => void;
}

/**
 * CK-4 — the context picker. The operator @-selects items (@doc @insight),
 * clicks Compose, and the substrate composes a §9.0-aware system_context
 * (personal_reading withheld on the non-owner path). The composed context is
 * surfaced up via ``onContextChange`` and the withheld / missing items are
 * rendered so the operator sees exactly what reached the model and what the
 * §9.0 gate held back.
 *
 * Delegates to ``composeContext`` (lib/api) so there is ONE documented client
 * for the /compose-context endpoint; the §9.0 fail-closed gate is enforced
 * server-side and described there, not re-implemented here.
 */
export default function ContextPicker({ onContextChange }: ContextPickerProps) {
  const [items, setItems] = useState<ContextItem[]>([]);
  const [kind, setKind] = useState<ContextItemKind>("doc");
  const [id, setId] = useState("");
  const [systemContext, setSystemContext] = useState("");
  const [withheld, setWithheld] = useState<string[]>([]);
  const [missing, setMissing] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const canCompose = items.length > 0 && !pending;

  const addItem = () => {
    const trimmed = id.trim();
    if (!trimmed) return;
    setItems((prev) => [...prev, { kind, id: trimmed }]);
    setId("");
  };

  const removeItem = (index: number) => {
    setItems((prev) => prev.filter((_, i) => i !== index));
  };

  const compose = async () => {
    if (!canCompose) return;
    setPending(true);
    setError(null);
    try {
      const data: ComposeContextResponse = await composeContext({ items });
      setSystemContext(data.system_context);
      setWithheld(data.withheld);
      setMissing(data.missing);
      onContextChange(data.system_context);
      emitWernerExperience("note_saved");
    } catch (err) {
      setError(
        err instanceof ApiError
          ? `Compose failed (HTTP ${err.status}).`
          : "Compose failed (network error).",
      );
      emitWernerExperience("fail");
    } finally {
      setPending(false);
    }
  };

  return (
    <div className="context-picker" role="group" aria-label="Context picker">
      <div className="context-picker__add">
        <select
          aria-label="Item kind"
          value={kind}
          onChange={(e) => setKind(e.target.value as ContextItemKind)}
        >
          <option value="doc">@doc</option>
          <option value="insight">@insight</option>
        </select>
        <input
          aria-label="Item id"
          value={id}
          onChange={(e) => setId(e.target.value)}
          placeholder="document or insight id"
          onKeyDown={(e) => {
            if (e.key === "Enter") addItem();
          }}
        />
        <button type="button" onClick={addItem} disabled={!id.trim()}>
          Add
        </button>
      </div>

      <ul className="context-picker__items">
        {items.map((item, i) => (
          <li key={`${item.kind}:${item.id}:${i}`}>
            <span>
              @{item.kind} {item.id}
            </span>
            <button
              type="button"
              onClick={() => removeItem(i)}
              aria-label={`Remove ${item.id}`}
            >
              remove
            </button>
          </li>
        ))}
      </ul>

      <button type="button" onClick={compose} disabled={!canCompose}>
        {pending ? "Composing…" : "Compose context"}
      </button>

      {error && <p role="alert">{error}</p>}
      {systemContext && (
        <pre data-testid="system-context">{systemContext}</pre>
      )}
      {withheld.length > 0 && (
        <p data-testid="withheld">Withheld: {withheld.join(", ")}</p>
      )}
      {missing.length > 0 && (
        <p data-testid="missing">Missing: {missing.join(", ")}</p>
      )}
    </div>
  );
}
