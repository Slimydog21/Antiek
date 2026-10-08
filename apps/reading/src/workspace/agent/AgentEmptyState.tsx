/**
 * AgentEmptyState.tsx — the pane's three canned prompts (SPR-07 M7), in
 * Antiek words. Keyboard: 1/2/3 pick them while the composer is empty and
 * untouched (composerKeys.cannedPromptForDigit); each sends with the
 * project context attached (AgentPane builds the system_context).
 */
export const CANNED_PROMPTS = [
  "What should I read next in this project?",
  "What is missing from this project's evidence?",
  "Where is this project's argument weakest?",
] as const;

export function AgentEmptyState({ onPrompt }: { onPrompt: (text: string, index: 1 | 2 | 3) => void }) {
  return (
    <div className="p-3 flex flex-col gap-1.5" data-agent-empty-state>
      <p className="text-xxs uppercase tracking-wider text-shadow-1 dark:text-moonlight">Ask the project</p>
      {CANNED_PROMPTS.map((prompt, i) => (
        <button
          key={prompt}
          type="button"
          onClick={() => onPrompt(prompt, (i + 1) as 1 | 2 | 3)}
          className="flex items-center gap-2 text-left text-sm text-ink dark:text-bright rounded px-2 py-1 hover:bg-ice-2 dark:hover:bg-charcoal-1 focus-visible:outline focus-visible:outline-2 focus-visible:outline-sun"
        >
          <kbd className="font-mono text-xxs text-shadow-1 dark:text-moonlight border border-hairline rounded px-1" aria-hidden="true">{i + 1}</kbd>
          <span>{prompt}</span>
        </button>
      ))}
    </div>
  );
}
