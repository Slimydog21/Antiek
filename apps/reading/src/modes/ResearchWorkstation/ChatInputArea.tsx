import OwnerModelUsagePicker from "../../components/ai/OwnerModelUsagePicker";
import LemonButton from "../../components/lemon/LemonButton";
import LemonTextarea from "../../components/lemon/LemonTextarea";
import {
  useOwnerModelController,
  type OwnerModelController,
} from "../../hooks/useOwnerModelController";
import {
  useResearchComposer,
  type ResearchComposerProps,
} from "./useResearchComposer";
function RootComposer(props: ResearchComposerProps) {
  const controller = useOwnerModelController({
    operationPrefix: "chat",
    policy: "strict-owner",
    allowHouse: true,
  });
  return <Composer {...props} controller={controller} />;
}
/** Root selection is deliberate; unsupported child DTOs keep their own route. */
export default function ChatInputArea(props: ResearchComposerProps) {
  const root =
    props.parentInvestigationId == null && props.spawnContext == null;
  return root ? <RootComposer {...props} /> : <Composer {...props} />;
}
function Composer({
  parentInvestigationId,
  spawnContext,
  placeholder,
  autoFocus,
  onSubmitted,
  controller,
}: ResearchComposerProps & { controller?: OwnerModelController }) {
  const {
    question,
    error,
    busy,
    editingDisabled,
    submit,
    changeQuestion,
    startSeparate,
    showUncertainty,
    submitDisabled,
  } = useResearchComposer({
    parentInvestigationId,
    spawnContext,
    onSubmitted,
    controller,
  });
  return (
    <div className="h-full flex flex-col p-3 bg-ice-1 dark:bg-charcoal-2 text-ink dark:text-bright">
      <div className="flex-1 min-h-0 flex flex-col">
        <LemonTextarea
          value={question}
          onChange={(event) => changeQuestion(event.target.value)}
          onSubmit={() => void submit()}
          placeholder={placeholder ?? "What do you want to research?"}
          autoFocus={autoFocus}
          disabled={editingDisabled}
          minRows={2}
          maxRows={10}
          className="font-serif text-base leading-relaxed"
        />
        {error && (
          <div className="text-xs font-mono text-emperor mt-2" role="status">
            {error}
          </div>
        )}
      </div>
      {controller && (
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <span className="text-xxs font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
            Model for this research
          </span>
          <OwnerModelUsagePicker
            controller={controller}
            allowHouse
            triggerAriaLabel="Model for this research"
          />
          {controller.selection.kind === "unavailable" && (
            <span className="text-xxs text-emperor">
              Selected model unavailable. Choose another explicitly.
            </span>
          )}
        </div>
      )}
      {showUncertainty && (
        <div className="mt-2 text-xs text-ink-soft">
          <p>
            A previous research request may have been accepted or charged.
            Starting separately does not cancel or replay it.
          </p>
          <LemonButton size="sm" variant="secondary" onClick={startSeparate}>
            Start a separate research
          </LemonButton>
        </div>
      )}
      <div className="mt-2 flex items-center justify-between gap-3">
        <div className="text-xs font-mono text-ink-mute dark:text-moonlight">
          <kbd className="border-2 border-ink dark:border-bright rounded px-1.5 text-xxs font-mono bg-ice-0 dark:bg-charcoal-1 shadow-[2px_2px_0_0_#0F1419] dark:shadow-[2px_2px_0_0_#8A7300] mr-1.5">
            ⌘ ↵
          </kbd>
          to submit · costs depend on the selected model and research steps
        </div>
        <LemonButton
          variant="primary"
          onClick={() => void submit()}
          disabled={submitDisabled}
        >
          {busy ? "…" : "Ask"}
        </LemonButton>
      </div>
    </div>
  );
}
