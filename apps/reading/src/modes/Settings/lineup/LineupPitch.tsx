import { GENERAL_SLOTS, type GeneralSlot } from "./inventory";
import { ModelCard } from "./ModelCard";
import type { LineupCard, LineupState } from "./lineup";
import { benchCards, occupant } from "./lineup";

/** Four starting positions — names are the product contract, not CSS labels. */
const PITCH_POSITIONS: readonly GeneralSlot[] = [
  "writer",
  "data miner",
  "data refinement",
  "data verification",
];

if (PITCH_POSITIONS.join("\0") !== GENERAL_SLOTS.join("\0")) {
  throw new Error("LineupPitch positions drifted from GENERAL_SLOTS");
}

export type Selection =
  | { kind: "slot"; slot: GeneralSlot }
  | { kind: "card"; cardId: string }
  | null;

type Props = {
  state: LineupState;
  cards: readonly LineupCard[];
  selection: Selection;
  onSelectSlot: (slot: GeneralSlot) => void;
  onSelectCard: (cardId: string) => void;
};

export function LineupPitch({
  state,
  cards,
  selection,
  onSelectSlot,
  onSelectCard,
}: Props) {
  const bench = benchCards(state, cards);

  return (
    <div data-testid="byot-general-lineup">
      <div className="byot-pitch" data-testid="byot-pitch" aria-label="Starting lineup">
        <div className="byot-pitch-midline" />
        <div className="byot-formation">
          {PITCH_POSITIONS.map((slot) => {
            const card = occupant(state, slot, cards);
            const slotSelected =
              selection?.kind === "slot" && selection.slot === slot;
            return (
              <div
                key={slot}
                className="byot-slot"
                data-slot={slot}
                data-testid={`lineup-slot-${slot}`}
              >
                <span className="byot-slot-name">{slot}</span>
                {card ? (
                  <ModelCard
                    card={card}
                    trim={slot}
                    selected={
                      slotSelected ||
                      (selection?.kind === "card" && selection.cardId === card.id)
                    }
                    onSelect={() => onSelectSlot(slot)}
                  />
                ) : (
                  <button
                    type="button"
                    className="byot-empty"
                    data-testid={`lineup-empty-${slot}`}
                    data-selected={slotSelected ? "true" : "false"}
                    aria-pressed={slotSelected}
                    onClick={() => onSelectSlot(slot)}
                  >
                    empty
                  </button>
                )}
              </div>
            );
          })}
        </div>
      </div>
      <div className="byot-bench" data-testid="byot-bench">
        <div className="byot-bench-label">Substitutes</div>
        {bench.length === 0 ? (
          <p className="text-sm text-ink-soft dark:text-starlight">
            Wire a model above, then tap a starter slot and a bench card to
            substitute.
          </p>
        ) : (
          <div className="byot-bench-row">
            {bench.map((card) => (
              <ModelCard
                key={card.id}
                card={card}
                trim="bench"
                selected={
                  selection?.kind === "card" && selection.cardId === card.id
                }
                onSelect={() => onSelectCard(card.id)}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
