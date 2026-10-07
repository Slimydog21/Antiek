import { useCallback, useRef, useState, type KeyboardEvent, type ReactNode } from "react";

import LemonButton from "../../components/lemon/LemonButton";
import LemonSelect from "../../components/lemon/LemonSelect";
import LemonTextarea from "../../components/lemon/LemonTextarea";
import { LemonTag, toast } from "../../components/lemon";
import { ErrorState } from "../../components/states";
import AIActionFailure from "../../shared/AIActionFailure";
import Thinking from "../../shared/Thinking";
import { CelebrateBurst } from "../../shared/delight";
import { seedThoughtPartner } from "../../components/ai/thoughtPartnerSeed";
import type { ResearchSourcePolicy, ResearchTier } from "../../lib/api";
import { useWorkspace } from "../../workspace/WorkspaceStore";
import { AISIDECAR_PANEL_ID } from "../../workspace/shortcuts";
import VoiceChaseButton from "../ResearchWorkstation/VoiceChaseButton";
import DropZone from "./DropZone";
import {
  CAP_COPY,
  MAX_ATTACHMENTS,
  REFUSED_UNTIL_INTAKE_COPY,
  acceptanceFor,
  classifyFile,
  classifyText,
} from "./intakeKinds";
import { derivePromptFor, modelKey, useProjectIntake } from "./useProjectIntake";

/**
 * ZenHome — the research door as one box (FFX-KPA SPR-03, dark behind
 * antiek.nav.zenhome at /zen).
 *
 * Type, speak, drop, or talk it through; submit creates a project and lands
 * the user inside it. Everything else that StartResearch shows (tier, source
 * policy, owner model) sits behind one Options disclosure, and nothing else is
 * above the fold: box + attach + voice + talk + submit + Options + the SPR-04
 * switch slot = 7 interactive elements (ZenHome.test.tsx counts them; an
 * eighth needs a written reason).
 *
 * What reaches a server today: typed text, a URL, a text file and a voice
 * note. Images, PDFs and Word documents are refused with honest copy and are
 * never read or uploaded until SPR-B's intake contract lands (intakeKinds.ts).
 *
 * Attachments are STAGED, not sent, when they arrive: nothing touches the
 * network until submit, so Escape (or ×) really takes one back. On submit the
 * staged items go through the same ingest calls StartResearch uses, then the
 * investigation starts through useProjectIntake.
 */

/** refs/agent-pane-refs.md pattern 18: the interview turn for "talk it through". */
export const INTERVIEW_PROMPT =
  "You are helping someone start a project in Antiek. Interview them: ask one thing at a time, " +
  "most important first. Draw out the goal, who it is for and in what voice, and where their " +
  "materials live. Stop asking as soon as they hand you something concrete; if what they gave " +
  "already states the assignment, start on it. When a choice helps, offer two to four short " +
  "options and say they can answer in their own words.";

/** Insert `text` at `caret`, with a leading space when the character before
 *  the caret is not whitespace (pattern 23: voice note at the caret). */
export function insertAtCaret(value: string, caret: number, text: string): { value: string; caret: number } {
  const at = Math.max(0, Math.min(caret, value.length));
  const before = value.slice(0, at);
  const after = value.slice(at);
  const insert = before.length > 0 && !/\s$/.test(before) ? ` ${text}` : text;
  return { value: before + insert + after, caret: at + insert.length };
}

type Staged =
  | { id: number; kind: "text-file"; name: string; text: string }
  | { id: number; kind: "url"; name: string; url: string };

const TIER_OPTIONS: ReadonlyArray<{ value: ResearchTier; label: string }> = [
  { value: "fast", label: "Fast" },
  { value: "deep", label: "Deep" },
];
const SOURCE_OPTIONS: ReadonlyArray<{ value: ResearchSourcePolicy; label: string }> = [
  { value: "operator_corpus", label: "Corpus" },
  { value: "web", label: "Web" },
  { value: "arxiv", label: "arXiv" },
  { value: "substack", label: "Substack" },
];

export default function ZenHome({ switchSlot }: { switchSlot?: ReactNode } = {}) {
  const intake = useProjectIntake();
  const {
    start,
    composerRef,
    question,
    setQuestion,
    editQuestion,
    promptDerived,
    setPromptDerived,
    attach,
    setAttach,
    absorbUrl,
    absorbText,
    submitProject,
    projectError,
    onTryAgain,
    celebrating,
  } = intake;
  const { startedId, phase, events, failed, failureReason, error, busy } = start;

  const [staged, setStaged] = useState<Staged[]>([]);
  const [notices, setNotices] = useState<string[]>([]);
  const [optionsOpen, setOptionsOpen] = useState(false);
  const [recording, setRecording] = useState(false);
  const [sending, setSending] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const nextId = useRef(1);
  // State updates land on the next render, so two mod+Enter presses in one
  // tick would both see `sending === false`. The ref closes that window.
  const sendingRef = useRef(false);

  const working = busy || sending;

  const deriveIfEmpty = useCallback((title: string) => {
    if (question.trim().length > 0) return;
    setQuestion(derivePromptFor(title));
    setPromptDerived(true);
  }, [question, setQuestion, setPromptDerived]);

  const stageUrl = useCallback((url: string, replaceQuestion = false) => {
    if (staged.length >= MAX_ATTACHMENTS) {
      setNotices([CAP_COPY]);
      return;
    }
    setStaged((s) => [...s, { id: nextId.current++, kind: "url", name: url, url }]);
    setNotices([`Attached ${url}.`]);
    if (replaceQuestion) {
      setQuestion(derivePromptFor(url));
      setPromptDerived(true);
    } else {
      deriveIfEmpty(url);
    }
  }, [staged.length, deriveIfEmpty, setQuestion, setPromptDerived]);

  const addFiles = useCallback(async (files: File[]) => {
    const lines: string[] = [];
    const refused: string[] = [];
    const accepted: Staged[] = [];
    let room = MAX_ATTACHMENTS - staged.length;
    let capped = false;
    for (const file of files) {
      const kind = classifyFile(file);
      const acceptance = acceptanceFor(kind);
      if (!acceptance.accepted || kind !== "text-file") {
        // Refused: the File is dropped here — never read, never uploaded.
        // TODO(ffx-nav-backend-intake): an accepted image/pdf/docx row stages
        // here once useProjectIntake can send it to the published route.
        if (!acceptance.accepted && !lines.includes(acceptance.copy)) lines.push(acceptance.copy);
        if (acceptance.accepted && !lines.includes(REFUSED_UNTIL_INTAKE_COPY)) lines.push(REFUSED_UNTIL_INTAKE_COPY);
        refused.push(file.name);
        continue;
      }
      if (room <= 0) {
        capped = true;
        continue;
      }
      room -= 1;
      accepted.push({ id: nextId.current++, kind: "text-file", name: file.name, text: await file.text() });
    }
    if (accepted.length > 0) {
      setStaged((s) => [...s, ...accepted]);
      lines.unshift(`Attached ${accepted.map((a) => a.name).join(", ")}.`);
      deriveIfEmpty(accepted[0].name);
    }
    if (refused.length > 0) lines.push(`Not attached: ${refused.join(", ")}.`);
    if (capped) lines.push(CAP_COPY);
    setNotices(lines);
  }, [staged.length, deriveIfEmpty]);

  const unstage = useCallback((id: number) => {
    const item = staged.find((s) => s.id === id);
    if (!item) return;
    const rest = staged.filter((s) => s.id !== id);
    setStaged(rest);
    setNotices([`Removed ${item.name}.`]);
    if (rest.length === 0 && promptDerived) {
      setQuestion("");
      setPromptDerived(false);
    }
  }, [staged, promptDerived, setQuestion, setPromptDerived]);

  const submitBox = useCallback(async () => {
    if (working || sendingRef.current) return;
    const text = question.trim();
    // A bare URL is material, not a question: attach it and show the derived
    // prompt for confirmation instead of asking "https://…".
    if (staged.length === 0 && classifyText(text)) {
      stageUrl(text, true);
      return;
    }
    if (text.length < 3) return;
    sendingRef.current = true;
    setSending(true);
    try {
      for (const item of staged) {
        const ok = item.kind === "url" ? await absorbUrl(item.url) : await absorbText(item.text, item.name);
        if (!ok) return; // the failure is on screen; the rest stay staged
        setStaged((s) => s.filter((x) => x.id !== item.id));
      }
      await submitProject();
    } finally {
      sendingRef.current = false;
      setSending(false);
    }
  }, [working, question, staged, stageUrl, absorbUrl, absorbText, submitProject]);

  const onTranscript = useCallback((transcript: string) => {
    const t = transcript.trim();
    if (!t) return;
    const ta = composerRef.current;
    const caret = ta ? ta.selectionStart : question.length;
    const next = insertAtCaret(question, caret, t);
    editQuestion(next.value);
    window.requestAnimationFrame(() => {
      const el = composerRef.current;
      if (!el) return;
      el.focus();
      el.setSelectionRange(next.caret, next.caret);
    });
  }, [composerRef, question, editQuestion]);

  const talk = useCallback(() => {
    const draft = question.trim();
    try {
      const ws = useWorkspace.getState();
      if (!ws.panels[AISIDECAR_PANEL_ID]) {
        ws.open("AISidecar", {}, { mode: "docked-right", title: "AI", id: AISIDECAR_PANEL_ID });
      }
      if (!useWorkspace.getState().panels[AISIDECAR_PANEL_ID]) throw new Error("agent pane did not open");
    } catch {
      toast.err("Couldn’t open the agent pane. Your draft is still here.");
      return;
    }
    // SPR-07 replaces this preview with the interview pane; until then the
    // existing AISidecar takes the same seed.
    seedThoughtPartner({
      ...(draft ? { prompt: draft } : {}),
      system_context: INTERVIEW_PROMPT,
      source_label: "zen-home",
    });
  }, [question]);

  const onBoxKeyDown = useCallback((e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key !== "Escape" || recording) return; // a live recording owns Escape
    const last = staged[staged.length - 1];
    if (!last) return;
    e.preventDefault();
    unstage(last.id);
  }, [recording, staged, unstage]);

  // ── Started: the id is back and the run is live; navigation follows on
  //    the first event or after the inherited 1.5 s grace. ──
  if (startedId && !failed) {
    return (
      <main className="h-full flex items-center justify-center px-6" aria-label="Zen home">
        <div className="max-w-md w-full text-center" role="status" aria-live="polite">
          <div className="relative flex items-center justify-center mb-4">
            {celebrating && <CelebrateBurst active size={48} className="absolute inset-0 items-center justify-center" />}
            <Thinking size={48} label={phase === "connecting" ? "Connecting to the investigation" : "The investigation is working"} />
          </div>
          <p className="text-base font-serif text-ink dark:text-bright">
            {phase === "connecting" ? "Starting your project…" : `Working on it… ${events.length} event${events.length === 1 ? "" : "s"}`}
          </p>
        </div>
      </main>
    );
  }

  const canSubmit = !working && question.trim().length >= 3;

  return (
    <main className="relative h-full flex flex-col items-center justify-center px-6" aria-label="Zen home">
      <div className="absolute top-4 right-4" data-zen-switch-slot>
        {switchSlot}
      </div>
      <h1 className="sr-only">Start a project</h1>
      <div className="w-full max-w-[720px]">
        <DropZone
          className="rounded-hog-lg border border-rule dark:border-charcoal-1 bg-ice-0 dark:bg-charcoal-2 shadow-z1 dark:shadow-z1-night p-3"
          onFiles={(files) => void addFiles(files)}
          onUrl={(url) => stageUrl(url)}
          disabled={working}
        >
          <div data-zen-drop>
            <LemonTextarea
              ref={composerRef}
              value={question}
              onChange={(e) => editQuestion(e.target.value)}
              onSubmit={() => void submitBox()}
              onKeyDown={onBoxKeyDown}
              placeholder="What are you working on?"
              aria-label="What are you working on?"
              autoFocus
              disabled={working}
              minRows={2}
              maxRows={12}
              className="font-serif text-lg leading-relaxed !border-0 !shadow-none !bg-transparent"
            />
            {promptDerived && (
              <p className="px-3 pt-1 text-xs font-sans text-ink-mute dark:text-moonlight">
                Suggested from your attachment. Edit it or start as is.
              </p>
            )}
            {staged.length > 0 && (
              <ul className="flex flex-wrap gap-2 px-3 pt-2" aria-label="Attachments">
                {staged.map((item) => (
                  <li key={item.id}>
                    <LemonTag>
                      <span>{item.name}</span>
                      <button
                        type="button"
                        aria-label={`Remove ${item.name}`}
                        onClick={() => unstage(item.id)}
                        className="leading-none text-ink dark:text-bright"
                      >
                        ×
                      </button>
                    </LemonTag>
                  </li>
                ))}
              </ul>
            )}
            <div className="flex flex-wrap items-center gap-2 pt-3">
              <LemonButton
                type="button"
                variant="tertiary"
                size="sm"
                aria-label="Attach a file"
                disabled={working}
                onClick={() => fileInputRef.current?.click()}
              >
                ＋ Attach
              </LemonButton>
              <input
                ref={fileInputRef}
                type="file"
                multiple
                className="hidden"
                tabIndex={-1}
                aria-label="Choose files"
                onChange={(e) => {
                  const files = Array.from(e.target.files ?? []);
                  if (files.length > 0) void addFiles(files);
                  e.target.value = "";
                }}
              />
              <VoiceChaseButton
                onTranscript={onTranscript}
                disabled={working}
                idleLabel="Voice"
                escapeCancels
                onRecordingChange={setRecording}
              />
              <LemonButton type="button" variant="tertiary" size="sm" aria-label="Talk it through" onClick={talk}>
                <span className="whitespace-nowrap">Talk it through</span>
                <span className="ml-1.5 rounded-full border border-rule dark:border-charcoal-1 px-1.5 text-xxs font-mono text-ink-mute dark:text-moonlight">
                  preview
                </span>
              </LemonButton>
              <span className="flex-1" />
              <LemonButton type="button" variant="primary" size="sm" disabled={!canSubmit} onClick={() => void submitBox()}>
                {working ? "Starting…" : "Start"}
              </LemonButton>
            </div>
          </div>
        </DropZone>

        <div role="status" aria-live="polite" className="min-h-[1.25rem] px-3 pt-2 text-sm font-sans text-ink dark:text-bright">
          {notices.map((line) => <p key={line}>{line}</p>)}
        </div>

        {attach.kind === "failed" && (
          <AIActionFailure
            title="Couldn’t absorb that"
            reason={attach.reason}
            onRetry={() => setAttach({ kind: "idle" })}
            retryLabel="Dismiss"
          />
        )}
        {failed && (
          <AIActionFailure title="The research didn’t complete" reason={failureReason} onRetry={onTryAgain} />
        )}
        {error &&
          (error.startsWith("Submit failed") ? (
            <ErrorState
              variant="inline"
              title="Couldn’t start the research"
              body="Your words are still here, so you can send them again."
              detail={error}
              onRetry={() => void submitBox()}
            />
          ) : (
            <p className="text-sm text-danger">{error}</p>
          ))}
        {projectError && <p className="text-sm text-danger">{projectError}</p>}

        <div className="pt-2">
          <button
            type="button"
            aria-expanded={optionsOpen}
            aria-controls="zen-options"
            onClick={() => setOptionsOpen((o) => !o)}
            className="rounded-hog px-2 py-1 text-xs font-sans text-ink dark:text-bright underline-offset-2 hover:underline"
          >
            Options
          </button>
          {optionsOpen && <ZenOptions id="zen-options" intake={intake} disabled={working} />}
        </div>
      </div>
    </main>
  );
}

function ZenOptions({ id, intake, disabled }: { id: string; intake: ReturnType<typeof useProjectIntake>; disabled: boolean }) {
  const { tier, setTier, sourcePolicy, toggleSourcePolicy, models, modelsState, modelChoice, setModelChoice, selectModel } = intake;
  return (
    <div id={id} className="mt-2 space-y-3 rounded-hog border border-rule dark:border-charcoal-1 bg-ice-0 dark:bg-charcoal-2 p-3">
      <LemonSelect
        value={modelChoice ? modelKey(modelChoice.provider_id, modelChoice.model_id) : "established"}
        onChange={(value) => (value === "established" ? setModelChoice(null) : selectModel(value))}
        options={[
          { value: "established", label: `Established ${tier} route` },
          ...models.map((m) => ({ value: modelKey(m.id, m.model_id), label: `${m.display_name} · ${m.model_id}` })),
        ]}
        placeholder={modelsState === "loading" ? "Checking executable models…" : "Choose an executable model"}
        aria-label="Model"
        fullWidth
      />
      {!modelChoice && (
        <div className="flex items-center gap-2" role="radiogroup" aria-label="Research depth">
          {TIER_OPTIONS.map((option) => (
            <button
              key={option.value}
              type="button"
              role="radio"
              aria-checked={tier === option.value}
              onClick={() => setTier(option.value)}
              className={`px-3 py-1 rounded-hog text-xs font-sans border border-rule ${tier === option.value ? "bg-sun text-ink" : "bg-ice-0 dark:bg-charcoal-2 text-ink dark:text-bright"}`}
            >
              {option.label}
            </button>
          ))}
        </div>
      )}
      <div role="group" aria-label="Sources" className="flex flex-wrap items-center gap-2">
        {SOURCE_OPTIONS.map((opt) => {
          const active = sourcePolicy.includes(opt.value);
          return (
            <button
              key={opt.value}
              type="button"
              aria-pressed={active}
              disabled={disabled}
              onClick={() => toggleSourcePolicy(opt.value)}
              className={
                "rounded-hog border px-2.5 py-1 text-xs font-sans " +
                (active
                  ? "border-sun-deep bg-sun/15 text-ink dark:text-bright"
                  : "border-rule dark:border-charcoal-1 bg-ice-0 dark:bg-charcoal-2 text-ink dark:text-bright")
              }
            >
              {opt.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}
