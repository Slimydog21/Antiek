import { extraActionSets, inventoryRecord } from "./classify";
import { ROLE_INVENTORY } from "./inventory";
import { ModelCard } from "./ModelCard";
import type { LineupCard, LineupState } from "./lineup";
import { resolveAction } from "./lineup";

type Props = {
  state: LineupState;
  cards: readonly LineupCard[];
  selectedAction: string | null;
  selectedCardId: string | null;
  onSelectAction: (actionSet: string) => void;
  onSelectCard: (cardId: string) => void;
};

export function AdvancedLineup({
  state,
  cards,
  selectedAction,
  selectedCardId,
  onSelectAction,
  onSelectCard,
}: Props) {
  const extras = extraActionSets();
  const classified = ROLE_INVENTORY.filter(
    (record) => record.classification !== "extra",
  );

  return (
    <div data-testid="byot-advanced-lineup" className="space-y-5">
      <p className="text-sm text-ink-soft dark:text-starlight">
        Pin a model to one action (thought_partner, user_agent, autocomplete,
        interviewer, wrestler, rlm_orchestrator, visual, transcription, tts,
        plus per-role overrides). The pin beats the general starter for that
        action only. Un-pinned extras stay empty; un-pinned pipeline roles
        follow their general slot.
      </p>
      <ActionGroup
        title="Specific actions"
        roles={extras}
        state={state}
        cards={cards}
        selectedAction={selectedAction}
        selectedCardId={selectedCardId}
        onSelectAction={onSelectAction}
      />
      <ActionGroup
        title="Per-role overrides"
        roles={classified.map((record) => record.role)}
        state={state}
        cards={cards}
        selectedAction={selectedAction}
        selectedCardId={selectedCardId}
        onSelectAction={onSelectAction}
      />
      <div>
        <div className="byot-bench-label">Available models</div>
        {cards.length === 0 ? (
          <p className="text-sm text-ink-soft dark:text-starlight">
            No wired models yet.
          </p>
        ) : (
          <div className="byot-bench-row">
            {cards.map((card) => (
              <ModelCard
                key={card.id}
                card={card}
                trim="bench"
                selected={selectedCardId === card.id}
                onSelect={() => onSelectCard(card.id)}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function ActionGroup({
  title,
  roles,
  state,
  cards,
  selectedAction,
  selectedCardId,
  onSelectAction,
}: {
  title: string;
  roles: readonly string[];
  state: LineupState;
  cards: readonly LineupCard[];
  selectedAction: string | null;
  selectedCardId: string | null;
  onSelectAction: (actionSet: string) => void;
}) {
  return (
    <section>
      <h3 className="font-serif text-base text-ink dark:text-bright mb-3">
        {title}
      </h3>
      <ul className="space-y-3">
        {roles.map((role) => {
          const record = inventoryRecord(role);
          const card = resolveAction(state, role, cards);
          const selected = selectedAction === role;
          return (
            <li
              key={role}
              className="flex flex-wrap items-center justify-between gap-3 rounded-hog border border-rule dark:border-slate-2 bg-ice-0 dark:bg-charcoal-2 px-3 py-2"
              data-testid={`advanced-slot-${role}`}
            >
              <div className="min-w-0">
                <p className="font-mono text-[12px] text-ink dark:text-bright">
                  {role}
                </p>
                <p className="text-xs text-ink-soft dark:text-starlight">
                  {record.summary}
                </p>
              </div>
              {card ? (
                <ModelCard
                  card={card}
                  trim={
                    record.classification === "extra"
                      ? "extra"
                      : record.classification
                  }
                  selected={
                    selected || selectedCardId === card.id
                  }
                  onSelect={() => onSelectAction(role)}
                />
              ) : (
                <button
                  type="button"
                  className="byot-empty"
                  style={{ minHeight: "4.5rem", width: "7.4rem" }}
                  data-selected={selected ? "true" : "false"}
                  aria-pressed={selected}
                  onClick={() => onSelectAction(role)}
                >
                  {record.classification === "extra"
                    ? "unassigned"
                    : "follows general"}
                </button>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
