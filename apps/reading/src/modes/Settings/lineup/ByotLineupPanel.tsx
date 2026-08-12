import { useEffect, useMemo, useState } from "react";
import LemonCard from "../../../components/lemon/LemonCard";
import { fetchUserModels, type UserModelRow } from "../../../api/settingsModels";
import { AdvancedLineup } from "./AdvancedLineup";
import { LineupPitch, type Selection } from "./LineupPitch";
import {
  emptyLineup,
  substitute,
  substituteAdvanced,
  type LineupCard,
  type LineupState,
} from "./lineup";
import type { GeneralSlot } from "./inventory";
import "./lineup.css";

const STORAGE_KEY = "antiek.byot.lineup.v1";

function cardsFromModels(models: UserModelRow[]): LineupCard[] {
  return models.map((model) => ({
    id: model.id,
    displayName: model.display_name,
    modelId: model.model_id,
    provider: model.provider_catalog_id ?? model.provider_kind,
  }));
}

function readStoredLineup(): LineupState {
  if (typeof window === "undefined") return emptyLineup();
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return emptyLineup();
    const parsed = JSON.parse(raw) as LineupState;
    const base = emptyLineup();
    return {
      starters: { ...base.starters, ...parsed.starters },
      overrides: parsed.overrides ?? {},
    };
  } catch {
    return emptyLineup();
  }
}

export default function ByotLineupPanel() {
  const [models, setModels] = useState<UserModelRow[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [state, setState] = useState<LineupState>(readStoredLineup);
  const [selection, setSelection] = useState<Selection>(null);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [advancedAction, setAdvancedAction] = useState<string | null>(null);
  const [advancedCardId, setAdvancedCardId] = useState<string | null>(null);

  const cards = useMemo(
    () => cardsFromModels(models ?? []),
    [models],
  );

  useEffect(() => {
    let cancelled = false;
    void fetchUserModels()
      .then((response) => {
        if (cancelled) return;
        setModels(response.models);
        setLoadError(null);
      })
      .catch(() => {
        if (cancelled) return;
        setLoadError("Can't load wired models for the lineup.");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  }, [state]);

  function applyGeneral(nextSlot: GeneralSlot, nextCardId: string) {
    setState((current) => substitute(current, nextSlot, nextCardId, cards));
    setSelection(null);
  }

  function onSelectSlot(slot: GeneralSlot) {
    if (selection?.kind === "card") {
      applyGeneral(slot, selection.cardId);
      return;
    }
    setSelection((current) =>
      current?.kind === "slot" && current.slot === slot ? null : { kind: "slot", slot },
    );
  }

  function onSelectBenchCard(cardId: string) {
    if (selection?.kind === "slot") {
      applyGeneral(selection.slot, cardId);
      return;
    }
    setSelection((current) =>
      current?.kind === "card" && current.cardId === cardId
        ? null
        : { kind: "card", cardId },
    );
  }

  function onSelectAdvancedAction(actionSet: string) {
    if (advancedCardId) {
      setState((current) =>
        substituteAdvanced(current, actionSet, advancedCardId, cards),
      );
      setAdvancedAction(null);
      setAdvancedCardId(null);
      return;
    }
    setAdvancedAction((current) => (current === actionSet ? null : actionSet));
  }

  function onSelectAdvancedCard(cardId: string) {
    if (advancedAction) {
      setState((current) =>
        substituteAdvanced(current, advancedAction, cardId, cards),
      );
      setAdvancedAction(null);
      setAdvancedCardId(null);
      return;
    }
    setAdvancedCardId((current) => (current === cardId ? null : cardId));
  }

  return (
    <LemonCard title="Starting lineup" elevation="z1" colour="glacial">
      <div className="p-4 space-y-4" data-testid="byot-lineup-panel">
        <p className="text-sm text-ink-soft dark:text-starlight font-serif italic">
          Four starters, one bench. Tap a position, then a substitute — same
          swap as a futbol lineup. Wired keys from Add model sit on the
          bench until they start.
        </p>
        {loadError && (
          <p className="text-sm text-red-700 dark:text-red-300 font-mono" role="alert">
            {loadError}
          </p>
        )}
        <LineupPitch
          state={state}
          cards={cards}
          selection={selection}
          onSelectSlot={onSelectSlot}
          onSelectCard={onSelectBenchCard}
        />
        <button
          type="button"
          className="text-sm font-semibold text-ink dark:text-bright underline underline-offset-4"
          data-testid="byot-advanced-toggle"
          aria-expanded={advancedOpen}
          onClick={() => setAdvancedOpen((open) => !open)}
        >
          {advancedOpen ? "Hide advanced settings" : "Advanced settings"}
        </button>
        {advancedOpen && (
          <AdvancedLineup
            state={state}
            cards={cards}
            selectedAction={advancedAction}
            selectedCardId={advancedCardId}
            onSelectAction={onSelectAdvancedAction}
            onSelectCard={onSelectAdvancedCard}
          />
        )}
      </div>
    </LemonCard>
  );
}
