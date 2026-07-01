import { useEffect, useMemo, useRef, useState } from "react";

import { apiFetch, type ParkedQuestionEntry } from "../../lib/api";
import {
  BRAINSTORM_SELECT_QUESTION_EVENT,
  getBrainstormQuestionSelection,
} from "./WatchForLaterPanel";

type ThoughtPartnerReply = {
  text: string;
  shape: "challenge" | "synthesis" | "extension" | "unknown";
  challenges: Array<{ condition: string; note_ids: string[] }>;
  synthesisText: string | null;
  extensions: Array<{
    sub_question: string;
    tag?: string | null;
    rationale?: string | null;
  }>;
  policyId: string | null;
  threadNodeId: string | null;
};

/**
 * BrainstormStation's active thought-partner panel.
 *
 * It binds to the selected watch-for-later question and sends a real
 * `/brainstorm/thought-partner` turn. The backend owns provider dispatch and
 * returns an honest 503 when no model key is configured; this panel surfaces
 * that state instead of fabricating a canned "assistant" answer.
 */
export default function ThoughtPartnerPanel() {
  const [selectedQuestion, setSelectedQuestion] =
    useState<ParkedQuestionEntry | null>(null);
  const [prompt, setPrompt] = useState("");
  const [pending, setPending] = useState(false);
  const [reply, setReply] = useState<ThoughtPartnerReply | null>(null);
  const [error, setError] = useState<string | null>(null);
  const requestGenerationRef = useRef(0);

  useEffect(() => {
    const applySelection = (question: ParkedQuestionEntry) => {
      requestGenerationRef.current += 1;
      setSelectedQuestion(question);
      setPrompt("");
      setPending(false);
      setReply(null);
      setError(null);
    };
    const latest = getBrainstormQuestionSelection();
    if (latest) applySelection(latest);
    const onSelect = (event: Event) => {
      const question = (event as CustomEvent<{ question?: ParkedQuestionEntry }>)
        .detail?.question;
      if (question) applySelection(question);
    };
    window.addEventListener(BRAINSTORM_SELECT_QUESTION_EVENT, onSelect);
    return () => {
      window.removeEventListener(BRAINSTORM_SELECT_QUESTION_EVENT, onSelect);
    };
  }, []);

  const contextLabel = useMemo(() => {
    if (!selectedQuestion) return "No parked question selected";
    return selectedQuestion.source_document_id
      ? `${selectedQuestion.source_investigation_id} / ${selectedQuestion.source_document_id}`
      : selectedQuestion.source_investigation_id;
  }, [selectedQuestion]);
  const selectedQuestionText = selectedQuestion?.question_text.trim() ?? "";

  async function sendThoughtPartner() {
    if (!selectedQuestion || !selectedQuestionText || !prompt.trim() || pending) {
      return;
    }
    const generation = ++requestGenerationRef.current;
    setPending(true);
    setError(null);
    setReply(null);
    try {
      const response = await apiFetch("/brainstorm/thought-partner", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          investigation_id: selectedQuestion.source_investigation_id,
          user_prompt: prompt.trim(),
          selected_notes: [
            {
              note_id: selectedQuestion.question_id,
              note_text: selectedQuestionText,
              source_event_ids: selectedQuestion.parent_event_id
                ? [selectedQuestion.parent_event_id]
                : [],
              source_investigation_id: selectedQuestion.source_investigation_id,
              source_document_id: selectedQuestion.source_document_id,
              anchor_region_id: selectedQuestion.anchor_region_id,
            },
          ],
        }),
      });
      if (!response.ok) {
        if (generation !== requestGenerationRef.current) return;
        const detail =
          response.status === 503
            ? "No provider keys configured yet. The thought partner will answer after activation SPR-03 provider-key setup."
            : `Thought partner unavailable (HTTP ${response.status}).`;
        setError(detail);
        return;
      }
      const data = (await response.json()) as {
        text?: string;
        shape?: string;
        challenges?: Array<{ condition?: string; note_ids?: string[] }>;
        synthesis_text?: string | null;
        extensions?: Array<{
          sub_question?: string;
          tag?: string | null;
          rationale?: string | null;
        }>;
        policy_id?: string | null;
        thread_node_id?: string | null;
      };
      if (generation !== requestGenerationRef.current) return;
      const shape =
        data.shape === "challenge" ||
        data.shape === "synthesis" ||
        data.shape === "extension"
          ? data.shape
          : "unknown";
      setReply({
        text: data.text ?? "",
        shape,
        challenges: (data.challenges ?? [])
          .map((challenge) => ({
            condition: challenge.condition?.trim() ?? "",
            note_ids: challenge.note_ids ?? [],
          }))
          .filter((challenge) => challenge.condition),
        synthesisText: data.synthesis_text?.trim() || null,
        extensions: (data.extensions ?? [])
          .map((extension) => ({
            sub_question: extension.sub_question?.trim() ?? "",
            tag: extension.tag?.trim() || null,
            rationale: extension.rationale?.trim() || null,
          }))
          .filter((extension) => extension.sub_question),
        policyId: data.policy_id ?? null,
        threadNodeId: data.thread_node_id ?? null,
      });
    } catch (e: unknown) {
      if (generation !== requestGenerationRef.current) return;
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      if (generation === requestGenerationRef.current) setPending(false);
    }
  }

  return (
    <div className="h-full overflow-y-auto bg-ice-1 dark:bg-charcoal-2 p-4 space-y-3">
      <header>
        <h3 className="text-xs font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
          Thought partner
        </h3>
      </header>
      <section className="rounded-md border border-rule dark:border-charcoal-1 bg-ice-0 dark:bg-charcoal-1 p-3">
        <p className="text-[10px] font-mono uppercase tracking-wide text-shadow-1 dark:text-moonlight">
          Selected question
        </p>
        {selectedQuestion ? (
          <>
            <p className="mt-1 text-sm font-serif leading-relaxed text-ink dark:text-bright">
              {selectedQuestion.question_text || "(no question text)"}
            </p>
            <p className="mt-2 text-[10.5px] font-mono text-ink-mute dark:text-moonlight">
              {contextLabel}
            </p>
          </>
        ) : (
          <p className="mt-1 text-xs italic leading-relaxed text-ink-mute dark:text-moonlight">
            Select a parked question from the watch-for-later panel.
          </p>
        )}
        {selectedQuestion && !selectedQuestionText && (
          <p className="mt-2 text-[10.5px] font-mono text-emperor">
            This parked question has no text to send.
          </p>
        )}
      </section>
      <label className="block space-y-1">
        <span className="text-[10px] font-mono uppercase tracking-wide text-shadow-1 dark:text-moonlight">
          Ask
        </span>
        <textarea
          value={prompt}
          onChange={(event) => setPrompt(event.target.value)}
          rows={5}
          placeholder="Challenge, synthesize, or extend this question..."
          className="w-full resize-none rounded-md border border-rule dark:border-charcoal-1 bg-ice-0 dark:bg-charcoal-1 px-3 py-2 text-sm text-ink dark:text-bright focus:outline-none focus:ring-2 focus:ring-sun"
        />
      </label>
      <button
        type="button"
        onClick={() => void sendThoughtPartner()}
        disabled={!selectedQuestion || !selectedQuestionText || !prompt.trim() || pending}
        className="w-full rounded-md bg-ink px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-shadow-2 disabled:bg-glacial-1 disabled:text-ink-mute dark:disabled:bg-charcoal-1"
      >
        {pending ? "Thinking..." : "Ask thought partner"}
      </button>
      {error && (
        <p className="rounded-md border border-emperor/30 bg-ice-0 dark:bg-charcoal-1 p-3 text-xs text-emperor">
          {error}
        </p>
      )}
      {reply && (
        <section className="rounded-md border border-rule dark:border-charcoal-1 bg-ice-0 dark:bg-charcoal-1 p-3">
          <p className="text-[10px] font-mono uppercase tracking-wide text-shadow-1 dark:text-moonlight">
            Reply{reply.shape !== "unknown" ? ` · ${reply.shape}` : ""}
          </p>
          {reply.shape === "challenge" && reply.challenges.length > 0 ? (
            <ul className="mt-2 space-y-2">
              {reply.challenges.map((challenge, index) => (
                <li
                  key={`${challenge.condition}-${index}`}
                  className="text-sm font-serif leading-relaxed text-ink dark:text-bright"
                >
                  <span>{challenge.condition}</span>
                  {challenge.note_ids.length > 0 && (
                    <span className="ml-2 font-mono text-[10.5px] text-ink-mute dark:text-moonlight">
                      {challenge.note_ids.join(", ")}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          ) : reply.shape === "extension" && reply.extensions.length > 0 ? (
            <ul className="mt-2 space-y-2">
              {reply.extensions.map((extension, index) => (
                <li
                  key={`${extension.sub_question}-${index}`}
                  className="text-sm font-serif leading-relaxed text-ink dark:text-bright"
                >
                  <span>{extension.sub_question}</span>
                  {extension.tag && (
                    <span className="ml-2 font-mono text-[10.5px] text-ink-mute dark:text-moonlight">
                      {extension.tag}
                    </span>
                  )}
                  {extension.rationale && (
                    <p className="mt-1 text-xs font-sans leading-relaxed text-ink-mute dark:text-moonlight">
                      {extension.rationale}
                    </p>
                  )}
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-2 whitespace-pre-line text-sm font-serif leading-relaxed text-ink dark:text-bright">
              {reply.synthesisText ?? reply.text}
            </p>
          )}
          {reply.policyId && (
            <p className="mt-2 text-[10.5px] font-mono text-ink-mute dark:text-moonlight">
              policy: {reply.policyId}
            </p>
          )}
          {reply.threadNodeId && (
            <p className="mt-2 text-[10.5px] font-mono text-ink-mute dark:text-moonlight">
              anchored thread: {reply.threadNodeId}
            </p>
          )}
        </section>
      )}
    </div>
  );
}
