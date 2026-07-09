/**
 * CollectiveResearchPanel — multi-select deep-research instances → one unit.
 *
 * Operator selects multiple spawn ids (from floating sessions) and merges
 * them via /engagement/collective into a cohesive prompt block.
 */

import { useCallback, useState } from "react";
import {
  fetchCollectiveResearch,
  type CollectiveResponse,
} from "../../api/engagement";

export type CollectiveResearchPanelProps = {
  /** Pre-listed spawn ids available for multi-select */
  availableSpawnIds: string[];
};

export function CollectiveResearchPanel({
  availableSpawnIds,
}: CollectiveResearchPanelProps) {
  const [selected, setSelected] = useState<string[]>([]);
  const [unit, setUnit] = useState<CollectiveResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const toggle = (id: string) => {
    setSelected((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    );
  };

  const merge = useCallback(async () => {
    if (selected.length < 1) return;
    setBusy(true);
    setError(null);
    try {
      const result = await fetchCollectiveResearch({ spawn_ids: selected });
      if (result.view_format !== "html") {
        throw new Error("collective view_format must be html");
      }
      setUnit(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, [selected]);

  return (
    <section
      className="collective-research-panel"
      data-view-format="html"
      aria-label="Collective deep research"
    >
      <header>
        <h2>Collective deep research</h2>
        <p className="meta">Merge multiple subagent instances into one prompt unit</p>
      </header>

      <ul className="spawn-list">
        {availableSpawnIds.map((id) => (
          <li key={id}>
            <label>
              <input
                type="checkbox"
                checked={selected.includes(id)}
                onChange={() => toggle(id)}
                disabled={busy}
              />{" "}
              <code>{id}</code>
            </label>
          </li>
        ))}
      </ul>

      <button
        type="button"
        onClick={() => void merge()}
        disabled={busy || selected.length < 1}
      >
        {busy ? "Merging…" : `Merge ${selected.length} spawn(s)`}
      </button>

      {error ? (
        <p className="error" role="alert">
          {error}
        </p>
      ) : null}

      {unit ? (
        <div className="collective-result">
          <p>
            collective <code>{unit.collective_id}</code> · spawns=
            {unit.spawn_count} · twins={unit.twin_count} · refs={unit.ref_count}
          </p>
          <pre className="prompt-block" data-testid="collective-prompt-block">
            {unit.prompt_block}
          </pre>
        </div>
      ) : null}
    </section>
  );
}

export default CollectiveResearchPanel;
