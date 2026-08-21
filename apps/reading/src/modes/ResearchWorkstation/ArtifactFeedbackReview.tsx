import { useEffect, useRef, useState } from "react";

import {
  createArtifactFeedback,
  getFeedbackThread,
  type FeedbackAnchor,
  type FeedbackThread,
} from "../../api/feedback";
import LemonButton from "../../components/lemon/LemonButton";
import { anchorFromRange, type ArtifactFeedbackSelection } from "./artifactFeedbackSelection";
import "./ArtifactFeedbackReview.css";

interface ReviewReceipt {
  artifactId: string;
  version: string;
  hash: string;
  sourceHash: string;
}

export interface ArtifactFeedbackReviewProps {
  investigationId: string;
  previewUrl: string;
  receipt: ReviewReceipt;
  title: string;
}

type ReviewState =
  | { kind: "waiting" }
  | {
      kind: "composing";
      selection: ArtifactFeedbackSelection;
      body: string;
      idempotencyKey: string;
    }
  | {
      kind: "submitting";
      selection: ArtifactFeedbackSelection;
      body: string;
      idempotencyKey: string;
    }
  | { kind: "active"; thread: FeedbackThread }
  | {
      kind: "error";
      selection: ArtifactFeedbackSelection;
      body: string;
      idempotencyKey: string;
      message: string;
    };

const TERMINAL_WORK_STATES = new Set([
  "replied",
  "declined",
  "approval_requested",
  "failed",
]);

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : "Feedback could not be saved.";
}

function feedbackAnchor(selection: ArtifactFeedbackSelection): FeedbackAnchor {
  return {
    normalization: selection.normalization,
    node_id: selection.node_id,
    node_text_sha256: selection.node_text_sha256,
    start_scalar: selection.start_scalar,
    end_scalar: selection.end_scalar,
    quote: selection.quote,
    prefix: selection.prefix,
    suffix: selection.suffix,
  };
}

export default function ArtifactFeedbackReview({
  investigationId,
  previewUrl,
  receipt,
  title,
}: ArtifactFeedbackReviewProps) {
  const [state, setState] = useState<ReviewState>({ kind: "waiting" });
  const disconnectRef = useRef<(() => void) | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => () => disconnectRef.current?.(), []);

  useEffect(() => {
    if (state.kind !== "composing" && state.kind !== "error") return;
    textareaRef.current?.focus();
  }, [state.kind]);

  useEffect(() => {
    if (state.kind !== "active" || TERMINAL_WORK_STATES.has(state.thread.work.state)) return;
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      void getFeedbackThread(state.thread.thread_id, controller.signal)
        .then((thread) => setState({ kind: "active", thread }))
        .catch(() => undefined);
    }, 5_000);
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [state]);

  const connectFrame = (frame: HTMLIFrameElement) => {
    disconnectRef.current?.();
    const frameDocument = frame.contentDocument;
    const frameWindow = frame.contentWindow;
    if (!frameDocument || !frameWindow) return;
    const capture = () => {
      const selection = frameWindow.getSelection();
      if (!selection || selection.rangeCount !== 1 || selection.isCollapsed) return;
      void anchorFromRange(selection.getRangeAt(0)).then((anchor) => {
        if (!anchor) return;
        setState({
          kind: "composing",
          selection: anchor,
          body: "",
          idempotencyKey: `feedback-${crypto.randomUUID()}`,
        });
      });
    };
    frameDocument.addEventListener("mouseup", capture);
    frameDocument.addEventListener("keyup", capture);
    disconnectRef.current = () => {
      frameDocument.removeEventListener("mouseup", capture);
      frameDocument.removeEventListener("keyup", capture);
    };
  };

  const updateBody = (body: string) => {
    setState((current) => {
      if (current.kind !== "composing" && current.kind !== "error") return current;
      return { ...current, kind: "composing", body };
    });
  };

  const submit = async () => {
    if (state.kind !== "composing" && state.kind !== "error") return;
    const command = state;
    const body = command.body.trim();
    if (!body) return;
    setState({ ...command, kind: "submitting", body });
    try {
      const thread = await createArtifactFeedback({
        artifactId: receipt.artifactId,
        version: Number(receipt.version),
        investigationId,
        contentSha256: receipt.hash,
        sourceSha256: receipt.sourceHash,
        anchor: feedbackAnchor(command.selection),
        bodyMarkdown: body,
        idempotencyKey: command.idempotencyKey,
      });
      setState({ kind: "active", thread });
    } catch (error) {
      setState({ ...command, kind: "error", body, message: messageOf(error) });
    }
  };

  const editable = state.kind === "composing" || state.kind === "error";

  return (
    <div className="artifact-review">
      <div className="artifact-review__paper">
        <iframe
          title={title}
          sandbox="allow-same-origin"
          src={previewUrl}
          onLoad={(event) => connectFrame(event.currentTarget)}
        />
      </div>
      <aside className="artifact-review__docket" aria-label="Research feedback docket">
        <header>
          <p className="artifact-review__eyebrow">Version {receipt.version} · margin docket</p>
          <h4>Steer the research</h4>
          <p>Select a sentence in one finding or open question, then leave a precise note.</p>
        </header>

        {state.kind === "waiting" ? (
          <p className="artifact-review__empty">No passage selected yet.</p>
        ) : null}

        {editable || state.kind === "submitting" ? (
          <div className="artifact-review__composer">
            <blockquote>“{state.selection.quote}”</blockquote>
            <p className="artifact-review__node">Node {state.selection.node_id}</p>
            <label>
              Comment for the research agent
              <textarea
                ref={textareaRef}
                value={state.body}
                maxLength={32768}
                rows={5}
                disabled={state.kind === "submitting"}
                onChange={(event) => updateBody(event.target.value)}
              />
            </label>
            {state.kind === "error" ? <p role="alert">{state.message}</p> : null}
            <LemonButton
              size="sm"
              disabled={state.kind === "submitting" || !state.body.trim()}
              onClick={() => void submit()}
            >
              {state.kind === "submitting" ? "Sending…" : "Send to research agent"}
            </LemonButton>
          </div>
        ) : null}

        {state.kind === "active" ? (
          <div className="artifact-review__thread" aria-live="polite">
            <p className="artifact-review__work-state">
              {state.thread.work.state === "queued"
                ? `Queued for ${state.thread.work.logical_worker_id}`
                : `Research work · ${state.thread.work.state}`}
            </p>
            <ol>
              {state.thread.items.map((item) => (
                <li key={item.item_id} data-author={item.author_kind}>
                  <span>{item.author_kind === "operator" ? "You" : "Research agent"}</span>
                  <p>{item.body_markdown}</p>
                </li>
              ))}
            </ol>
          </div>
        ) : null}
      </aside>
    </div>
  );
}
