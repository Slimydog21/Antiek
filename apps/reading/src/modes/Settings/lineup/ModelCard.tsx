import type { GeneralSlot } from "./inventory";
import type { LineupCard } from "./lineup";

const RATINGS: Record<GeneralSlot | "extra" | "bench", string> = {
  writer: "WR",
  "data miner": "MN",
  "data refinement": "RF",
  "data verification": "VF",
  extra: "EX",
  bench: "SUB",
};

type Props = {
  card: LineupCard;
  trim: GeneralSlot | "extra" | "bench";
  selected: boolean;
  onSelect: () => void;
};

export function ModelCard({ card, trim, selected, onSelect }: Props) {
  return (
    <button
      type="button"
      className="byot-card"
      data-testid={`lineup-card-${card.id}`}
      data-trim={trim}
      data-selected={selected ? "true" : "false"}
      aria-pressed={selected}
      onClick={onSelect}
    >
      <div className="flex items-start justify-between gap-2">
        <span className="byot-card-rating">{RATINGS[trim]}</span>
        <span className="byot-card-pos">{trim}</span>
      </div>
      <span className="byot-card-name">{card.displayName}</span>
      <span className="byot-card-meta">{card.modelId}</span>
      <span className="byot-card-meta">{card.provider}</span>
    </button>
  );
}
