import { classifyRole } from "./classify";
import { GENERAL_SLOTS, type GeneralSlot } from "./inventory";

export type LineupCard = {
  id: string;
  displayName: string;
  modelId: string;
  provider: string;
};

export type LineupState = {
  starters: Record<GeneralSlot, string | null>;
  overrides: Record<string, string | null>;
};

export function emptyLineup(): LineupState {
  return {
    starters: {
      writer: null,
      "data miner": null,
      "data refinement": null,
      "data verification": null,
    },
    overrides: {},
  };
}

function cardById(
  cards: readonly LineupCard[],
  id: string | null,
): LineupCard | null {
  if (!id) return null;
  return cards.find((card) => card.id === id) ?? null;
}

/**
 * Put `replacementId` into `slot`.
 *
 * - If the replacement already starts at another general slot, the two
 *   occupants swap (FIFA substitution between two starters).
 * - Otherwise the previous occupant returns to the bench (derived: any
 *   card not occupying a starter slot).
 * - `replacementId === null` clears the slot.
 */
export function substitute(
  state: LineupState,
  slot: GeneralSlot,
  replacementId: string | null,
  cards: readonly LineupCard[],
): LineupState {
  if (replacementId !== null && !cards.some((card) => card.id === replacementId)) {
    throw new Error(`Unknown card ${JSON.stringify(replacementId)}`);
  }
  const previous = state.starters[slot];
  const nextStarters: Record<GeneralSlot, string | null> = {
    ...state.starters,
    [slot]: replacementId,
  };
  if (replacementId !== null) {
    for (const other of GENERAL_SLOTS) {
      if (other !== slot && nextStarters[other] === replacementId) {
        nextStarters[other] = previous;
      }
    }
  }
  return { starters: nextStarters, overrides: state.overrides };
}

/**
 * Pin a model to one named action/behavior set. Null clears the pin so
 * the general-category starter applies again.
 */
export function substituteAdvanced(
  state: LineupState,
  actionSet: string,
  replacementId: string | null,
  cards: readonly LineupCard[],
): LineupState {
  if (replacementId !== null && !cards.some((card) => card.id === replacementId)) {
    throw new Error(`Unknown card ${JSON.stringify(replacementId)}`);
  }
  classifyRole(actionSet);
  return {
    starters: state.starters,
    overrides: { ...state.overrides, [actionSet]: replacementId },
  };
}

export function resolveAction(
  state: LineupState,
  actionSet: string,
  cards: readonly LineupCard[],
): LineupCard | null {
  const overrideId = state.overrides[actionSet];
  if (overrideId) {
    return cardById(cards, overrideId);
  }
  const classification = classifyRole(actionSet);
  if (classification === "extra") {
    return null;
  }
  return cardById(cards, state.starters[classification]);
}

export function occupant(
  state: LineupState,
  slot: GeneralSlot,
  cards: readonly LineupCard[],
): LineupCard | null {
  return cardById(cards, state.starters[slot]);
}

export function benchCards(
  state: LineupState,
  cards: readonly LineupCard[],
): LineupCard[] {
  const occupied = new Set(
    GENERAL_SLOTS.map((slot) => state.starters[slot]).filter(
      (id): id is string => id !== null,
    ),
  );
  return cards.filter((card) => !occupied.has(card.id));
}
