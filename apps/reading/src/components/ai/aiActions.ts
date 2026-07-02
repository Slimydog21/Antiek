/**
 * AI tool-call protocol.
 *
 *   The AISidecar (and any future "AI inside a panel" surface) accepts
 *   structured ACTIONS from the assistant — not just prose. The
 *   assistant's reply may include a trailing `@@actions` JSON block
 *   listing actions to dispatch into the workspace store:
 *
 *     <prose body>
 *
 *     @@actions
 *     [
 *       {"kind": "open_panel", "panel_kind": "PdfViewer",
 *        "props": {"documentId": "doc-123", "initialPage": 12},
 *        "mode": "floating", "title": "Q4 risk model · p.12"},
 *       {"kind": "add_to_notebook",
 *        "notebook_id": "scratch",
 *        "block": {"kind": "note", "text": "Worth chasing."}}
 *     ]
 *     @@end
 *
 *   This file owns the schema, the parser, the executor + the
 *   serialiser that builds workspace-context for the assistant's
 *   request side. The protocol is intentionally narrow — a small
 *   closed set of actions — because we want the model to be a
 *   *participant* in the workspace, not a shell with arbitrary
 *   power.
 *
 *   Why this shape (vs. function-calling APIs):
 *     - The substrate's `/thought-partner` endpoint is provider-
 *       agnostic. Different operators may route it to different
 *       models (Claude, GPT, a local Qwen, Anthropic compatibility
 *       on xAI). Tool-call APIs vary; a markdown-style sentinel
 *       works on every model.
 *     - The actions are a CLOSED ENUM. The model can't smuggle
 *       arbitrary code through. Anything outside the enum is
 *       parsed-and-dropped + reported in dev mode.
 *     - The actions are EXECUTED IN THE OPERATOR'S CLIENT. The
 *       substrate never decides to open a panel; the model never
 *       directly touches localStorage. Everything happens after
 *       the operator sees the reply.
 *     - Each action is REVERSIBLE. The executor returns an undo
 *       handle that the AISidecar surfaces as a clickable pill.
 */

import type { PanelKind, PanelMode } from "../../workspace/panel.types";
import { useWorkspace } from "../../workspace/WorkspaceStore";
import { postTypedEvent, undoAiAction } from "../../lib/api";
import type { AIActionAppliedPayload, AIActionUndonePayload } from "../../generated/types";

// ─── Action schema ───────────────────────────────────────────────────

export type AiAction =
  | {
      kind: "open_panel";
      /** Must be in `PanelKind`. Unknown kinds are dropped. */
      panel_kind: PanelKind;
      props?: Record<string, unknown>;
      mode?: PanelMode;
      title?: string;
      /** Stable id so re-dispatching idempotently focuses. */
      id?: string;
    }
  | {
      kind: "focus_panel";
      /** The panel id to focus. */
      id: string;
    }
  | {
      kind: "close_panel";
      id: string;
    }
  | {
      kind: "set_panel_mode";
      id: string;
      mode: PanelMode;
    }
  | {
      kind: "add_to_notebook";
      notebook_id: string;
      block: {
        /** One of the slash-menu block names. */
        kind:
          | "note"
          | "claim_card"
          | "region_embed"
          | "cross_doc_link"
          | "master_section"
          | "question_card"
          | "chat_exchange"
          | "image"
          | "latex";
        attrs?: Record<string, unknown>;
        text?: string;
      };
    }
  | {
      kind: "chase_question";
      text: string;
      investigation_id?: string;
    }
  | {
      kind: "toast";
      level: "info" | "ok" | "warn" | "err";
      message: string;
    };

type NotebookActionBlock = Extract<AiAction, { kind: "add_to_notebook" }>["block"];

function parseStoredEtag(value: string | null): number {
  if (value === null) return 0;
  const trimmed = value.trim();
  if (!/^\d+$/.test(trimmed)) return 0;
  const n = Number(trimmed);
  return Number.isSafeInteger(n) ? n : 0;
}

// ─── Parser ──────────────────────────────────────────────────────────

const ACTIONS_FENCE_OPEN = /(?:^|\n)\s*@@actions\s*\n/;
const ACTIONS_FENCE_CLOSE = /\n\s*@@end\s*$/;

export type ParsedAssistantReply = {
  /** The prose body with the @@actions block stripped. */
  prose: string;
  /** Parsed actions, after schema validation. */
  actions: AiAction[];
  /** Raw text that failed to parse, surfaced in dev for debugging. */
  parseErrors: string[];
};

const VALID_ACTION_KINDS = new Set<AiAction["kind"]>([
  "open_panel",
  "focus_panel",
  "close_panel",
  "set_panel_mode",
  "add_to_notebook",
  "chase_question",
  "toast",
]);

/**
 * Parse an assistant reply. Returns the stripped prose + structured
 * actions. Tolerant of:
 *   - missing fence (just returns prose, no actions)
 *   - malformed JSON (parse error reported; prose returned)
 *   - schema mismatch on individual action objects (drop + report;
 *     keep the rest)
 */
export function parseAssistantReply(raw: string): ParsedAssistantReply {
  const errors: string[] = [];
  const openMatch = raw.match(ACTIONS_FENCE_OPEN);
  if (!openMatch || openMatch.index === undefined) {
    return { prose: raw.trim(), actions: [], parseErrors: [] };
  }
  const prose = raw.slice(0, openMatch.index).trim();
  let actionsText = raw.slice(openMatch.index + openMatch[0].length);
  // Optional trailing @@end fence
  const closeMatch = actionsText.match(ACTIONS_FENCE_CLOSE);
  if (closeMatch && closeMatch.index !== undefined) {
    actionsText = actionsText.slice(0, closeMatch.index);
  }
  actionsText = actionsText.trim();
  if (!actionsText) {
    return { prose, actions: [], parseErrors: [] };
  }

  let parsed: unknown;
  try {
    parsed = JSON.parse(actionsText);
  } catch (e) {
    errors.push(
      `JSON parse error: ${e instanceof Error ? e.message : String(e)}`,
    );
    return { prose, actions: [], parseErrors: errors };
  }
  if (!Array.isArray(parsed)) {
    errors.push("Expected an array of actions; got " + typeof parsed);
    return { prose, actions: [], parseErrors: errors };
  }

  const actions: AiAction[] = [];
  for (const item of parsed) {
    if (typeof item !== "object" || item === null) {
      errors.push("Skipped non-object action entry");
      continue;
    }
    const k = (item as { kind?: string }).kind;
    if (typeof k !== "string" || !VALID_ACTION_KINDS.has(k as AiAction["kind"])) {
      errors.push(`Unknown action kind: ${JSON.stringify(k)}`);
      continue;
    }
    // Light shape validation — defer the strict typing to the executor.
    actions.push(item as AiAction);
  }

  return { prose, actions, parseErrors: errors };
}

// ─── Executor ────────────────────────────────────────────────────────

/**
 * A side-effecting record of a dispatched action. The AISidecar
 * surfaces these as pills below the reply so the operator can see
 * what the AI did and undo it.
 */
export type DispatchedAction = {
  action: AiAction;
  /** A one-line summary the UI renders ("📓 Added a note to scratch"). */
  label: string;
  /** Undo handle — calling it reverses the action where possible. */
  undo: (() => void | Promise<void>) | null;
  /** Event-log id for the applied action, when substrate recording is enabled. */
  appliedEventId?: Promise<string | null>;
  /** Timestamp for ordering / display. */
  at: number;
};

/**
 * Context required to emit ``ai.action.applied`` events to the substrate
 * event log per master-spec §5.5 + §13.8 + PostHog Wedge 4. When this
 * context is provided, ``dispatchAiAction`` fires a typed event after
 * the action mutates the workspace and wraps the returned ``undo`` to
 * emit a matching ``ai.action.undone`` on invocation.
 *
 * When the context is omitted (legacy callers, tests), the action still
 * dispatches and the undo still works — only the event-log audit trail
 * is skipped.
 */
export interface AiActionContext {
  /** The operator's natural-language prompt that triggered the assistant
   * reply containing this action. Substrate validates min_length=1. */
  operator_prompt: string;
  /** Investigation id the AI sidecar session is attached to. Substrate
   * groups events by investigation. */
  investigation_id: string;
}

/** Describes WHICH substrate state the action mutated and what the
 * before/after snapshots looked like — the bridge data that lets the
 * substrate event log replay the trajectory. */
interface AiEventDescriptor {
  target_kind: AIActionAppliedPayload["target_kind"];
  target_id: string;
  prev_state: Record<string, unknown>;
  next_state: Record<string, unknown>;
  summary: string;
}

/** SHA-256 hex via Web Crypto. Browser-only; on Node test envs the
 * caller falls back to a deterministic stub (see usage in
 * ``recordAiActionApplied``). */
async function sha256Hex(s: string): Promise<string> {
  if (typeof crypto === "undefined" || !crypto.subtle) {
    // Test env: emit a non-cryptographic but deterministic placeholder
    // so the event still validates against the substrate schema.
    let h = 0;
    for (let i = 0; i < s.length; i++) h = ((h << 5) - h + s.charCodeAt(i)) | 0;
    return "stub-" + (h >>> 0).toString(16).padStart(8, "0");
  }
  const buf = new TextEncoder().encode(s);
  const hash = await crypto.subtle.digest("SHA-256", buf);
  return Array.from(new Uint8Array(hash))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

/** Fire-and-forget POST of ``ai.action.applied``. Returns the resulting
 * event_id (for the undo-event's inverted_event_id) or null on failure. */
async function recordAiActionApplied(
  ctx: AiActionContext,
  desc: AiEventDescriptor,
): Promise<string | null> {
  try {
    const prevJson = JSON.stringify(desc.prev_state);
    const hash = await sha256Hex(desc.target_kind + ":" + desc.target_id + ":" + prevJson);
    const payload: AIActionAppliedPayload = {
      action_type: "ai.action.applied",
      target_kind: desc.target_kind,
      target_id: desc.target_id,
      operator_prompt: ctx.operator_prompt,
      prev_state: desc.prev_state,
      next_state: desc.next_state,
      prev_state_hash: hash,
      summary: desc.summary,
    };
    const resp = await postTypedEvent({
      investigation_id: ctx.investigation_id,
      payload,
      role: "ai_sidecar",
    });
    return resp.event_id;
  } catch {
    // Event log is best-effort observability; never block the action.
    return null;
  }
}

/** Fire-and-forget POST of ``ai.action.undone``. */
async function recordAiActionUndone(
  ctx: AiActionContext,
  invertedEventId: string,
  desc: AiEventDescriptor,
): Promise<void> {
  try {
    const payload: AIActionUndonePayload = {
      action_type: "ai.action.undone",
      inverted_event_id: invertedEventId,
      target_kind: desc.target_kind,
      target_id: desc.target_id,
      reason: "operator_undo",
    };
    await postTypedEvent({
      investigation_id: ctx.investigation_id,
      payload,
      role: "ai_sidecar",
    });
  } catch {
    // Event log is best-effort observability; never block the undo.
  }
}

/** Execute a single parsed action. Returns a DispatchedAction record.
 *
 * If ``context`` is supplied, the bridge fires ``ai.action.applied``
 * to the substrate event log after the action mutates state, and
 * wraps the returned ``undo`` callable to emit ``ai.action.undone``
 * on invocation per master-spec §5.5 + §13.8. */
export function dispatchAiAction(
  action: AiAction,
  context?: AiActionContext,
): DispatchedAction {
  const ws = useWorkspace.getState();
  const at = Date.now();
  const restoreFocus = (id: string | null) => {
    if (id) {
      useWorkspace.getState().focus(id);
    } else {
      useWorkspace.setState({ focusedPanelId: null });
    }
  };

  /** Wrap a result with event-log bridging. Records ai.action.applied
   * and wraps undo to route through the substrate /ai/undo path first. */
  const withEventLog = (
    d: DispatchedAction,
    descriptor: AiEventDescriptor | null,
  ): DispatchedAction => {
    if (!context || !descriptor) return d;
    const eventIdPromise = recordAiActionApplied(context, descriptor);
    if (d.undo === null) return { ...d, appliedEventId: eventIdPromise };
    const originalUndo = d.undo;
    return {
      ...d,
      appliedEventId: eventIdPromise,
      undo: async () => {
        const eventId = await eventIdPromise;
        if (eventId) {
          try {
            await undoAiAction({
              event_id: eventId,
              investigation_id: context.investigation_id,
            });
            await originalUndo();
            return;
          } catch {
            // Fall back to the local inverse below. UI-layout actions may be
            // client-owned; failed audit writes must not strand the operator.
          }
        }

        await originalUndo();
        if (eventId) {
          await recordAiActionUndone(context, eventId, descriptor);
        }
      },
    };
  };

  switch (action.kind) {
    case "open_panel": {
      // Idempotent — re-firing the same action focuses the existing panel.
      const id =
        action.id ??
        `ai:${action.panel_kind}:${JSON.stringify(action.props ?? {})}`;
      const wasOpen = Boolean(ws.panels[id]);
      const prevFocus = ws.focusedPanelId;
      const prevDescriptor = wasOpen ? ws.panels[id] : null;
      ws.open(
        action.panel_kind,
        (action.props ?? {}) as Record<string, unknown>,
        {
          id,
          mode: action.mode ?? "floating",
          title: action.title,
        },
      );
      const descriptor: AiEventDescriptor = {
        target_kind: "ui_layout",
        target_id: id,
        prev_state: {
          open: wasOpen,
          focused_id: prevFocus,
          ...(prevDescriptor
            ? { kind: prevDescriptor.kind, mode: prevDescriptor.mode }
            : {}),
        },
        next_state: {
          open: true,
          focused_id: id,
          kind: action.panel_kind,
          mode: action.mode ?? "floating",
          title: action.title ?? "",
        },
        summary: `open_panel ${action.panel_kind}`,
      };
      return withEventLog(
        {
          action,
          label: `🪟 Opened ${action.panel_kind}${
            action.title ? " · " + action.title : ""
          }`,
          undo: wasOpen
            ? () => restoreFocus(prevFocus)
            : () => {
                useWorkspace.getState().close(id);
                restoreFocus(prevFocus);
              },
          at,
        },
        descriptor,
      );
    }

    case "focus_panel": {
      const prevFocus = ws.focusedPanelId;
      ws.focus(action.id);
      const descriptor: AiEventDescriptor = {
        target_kind: "ui_layout",
        target_id: action.id,
        prev_state: { focused_id: prevFocus },
        next_state: { focused_id: action.id },
        summary: `focus_panel ${action.id}`,
      };
      return withEventLog(
        {
          action,
          label: `🎯 Focused ${action.id}`,
          undo: () => restoreFocus(prevFocus),
          at,
        },
        descriptor,
      );
    }

    case "close_panel": {
      const existing = ws.panels[action.id];
      const prevFocus = ws.focusedPanelId;
      ws.close(action.id);
      const descriptor: AiEventDescriptor = {
        target_kind: "ui_layout",
        target_id: action.id,
        prev_state: existing
          ? {
              open: true,
              focused_id: prevFocus,
              kind: existing.kind,
              mode: existing.mode,
            }
          : { open: false, focused_id: prevFocus },
        next_state: { open: false },
        summary: `close_panel ${action.id}`,
      };
      return withEventLog(
        {
          action,
          label: `❌ Closed ${action.id}`,
          // Best-effort undo: reopen at the previous descriptor.
          undo: existing
            ? () => {
                useWorkspace.getState().open(existing.kind, existing.props, {
                  id: existing.id,
                  mode: existing.mode,
                  title: existing.title,
                });
                restoreFocus(prevFocus);
              }
            : null,
          at,
        },
        descriptor,
      );
    }

    case "set_panel_mode": {
      const before = ws.panels[action.id]?.mode;
      ws.setMode(action.id, action.mode);
      const descriptor: AiEventDescriptor = {
        target_kind: "ui_layout",
        target_id: action.id,
        prev_state: { mode: before ?? null },
        next_state: { mode: action.mode },
        summary: `set_panel_mode ${action.id} → ${action.mode}`,
      };
      return withEventLog(
        {
          action,
          label: `↔ ${action.id} → ${action.mode}`,
          undo: before
            ? () => useWorkspace.getState().setMode(action.id, before)
            : null,
          at,
        },
        descriptor,
      );
    }

    case "add_to_notebook": {
      const notebookId = nonEmptyString(action.notebook_id);
      const block = safeNotebookActionBlock(action.block);
      if (!notebookId || !block) {
        return {
          action,
          label: "Skipped invalid notebook action",
          undo: null,
          at,
        };
      }
      // The notebook editor consumes a localStorage-backed HTML string;
      // we append a custom-element tag the TipTap NodeView extensions
      // recognise. (See modes/Notebook/Editor.tsx for the storage
      // shape + Notebook/blocks/*.tsx for the parseHTML hooks.)
      //
      // After the write, dispatch a same-window custom event so an
      // open NotebookEditor instance with the matching notebookId can
      // reload its content. Cross-tab consumers also get the standard
      // browser `storage` event; same-tab consumers need this custom
      // signal because `storage` only fires across tabs.
      const html = aiBlockToHtml(block);
      const lsKey = "antiek.notebook." + notebookId;
      const etagKey = lsKey + ".etag";
      let previous: string | null = null;
      let prevEtag = 0;
      let nextEtag = 0;
      try {
        previous = window.localStorage.getItem(lsKey);
        const existing = previous ?? "<p></p>";
        const current = window.localStorage.getItem(etagKey);
        prevEtag = parseStoredEtag(current);
        nextEtag = prevEtag + 1;
        const appended = existing.replace(
          /<\/body>\s*$/,
          "",
        ) + "\n" + html;
        window.localStorage.setItem(lsKey, appended);
        window.localStorage.setItem(etagKey, String(nextEtag));
        // Same-tab signal: editors keyed by `notebook_id` reload.
        window.dispatchEvent(
          new CustomEvent("antiek:notebook:appended", {
            detail: { notebookId, etag: nextEtag },
          }),
        );
      } catch {
        // ignore quota; the operator sees the action label without effect
      }
      const descriptor: AiEventDescriptor = {
        target_kind: "notebook",
        target_id: notebookId,
        prev_state: { etag: prevEtag, html: previous },
        next_state: {
          etag: nextEtag,
          block_kind: block.kind,
          appended_html: html,
        },
        summary: `add_to_notebook ${notebookId} +1 ${block.kind}`,
      };
      return withEventLog(
        {
          action,
          label: `📓 Added a ${block.kind} to “${notebookId}”`,
          undo: () => {
            try {
              if (previous === null) {
                window.localStorage.removeItem(lsKey);
              } else {
                window.localStorage.setItem(lsKey, previous);
              }
              if (prevEtag <= 0) {
                window.localStorage.removeItem(etagKey);
              } else {
                window.localStorage.setItem(etagKey, String(prevEtag));
              }
              window.dispatchEvent(
                new CustomEvent("antiek:notebook:appended", {
                  detail: { notebookId, etag: prevEtag, force: true },
                }),
              );
            } catch {
              // Local notebook storage is best-effort; never strand the
              // operator in the AI action log if browser storage fails.
            }
          },
          at,
        },
        descriptor,
      );
    }

    case "chase_question": {
      const panelId = `chase:${action.text.slice(0, 32)}`;
      const wasOpen = Boolean(ws.panels[panelId]);
      const prevFocus = ws.focusedPanelId;
      ws.open(
        "Chase",
        {
          spawnContext: action.text,
          parentInvestigationId:
            action.investigation_id ?? context?.investigation_id ?? "__sidecar__",
        },
        {
          id: panelId,
          mode: "floating",
          title: "Chase",
        },
      );
      const descriptor: AiEventDescriptor = {
        target_kind: "investigation_chase",
        target_id: panelId,
        prev_state: { open: wasOpen, focused_id: prevFocus },
        next_state: {
          open: true,
          focused_id: panelId,
          spawn_context: action.text,
          parent_investigation_id:
            action.investigation_id ?? context?.investigation_id ?? "__sidecar__",
        },
        summary: `chase_question "${action.text.slice(0, 64)}"`,
      };
      return withEventLog(
        {
          action,
          label: `🔍 Chasing: “${action.text.slice(0, 48)}${
            action.text.length > 48 ? "…" : ""
          }”`,
          undo: () => {
            if (wasOpen) {
              restoreFocus(prevFocus);
            } else {
              useWorkspace.getState().close(panelId);
              restoreFocus(prevFocus);
            }
          },
          at,
        },
        descriptor,
      );
    }

    case "toast": {
      // The toast helper is imported dynamically to avoid a hard
      // dep cycle (LemonToast → React → AISidecar).
      void import("../lemon/LemonToast").then(({ toast }) => {
        const fn =
          action.level === "ok"
            ? toast.ok
            : action.level === "warn"
              ? toast.warn
              : action.level === "err"
                ? toast.err
                : toast.info;
        fn(action.message);
      });
      return {
        action,
        label: `🍋 Toast (${action.level}): ${action.message}`,
        undo: null,
        at,
      };
    }
  }
}

const NOTEBOOK_ACTION_BLOCK_KINDS = new Set<NotebookActionBlock["kind"]>([
  "note",
  "claim_card",
  "region_embed",
  "cross_doc_link",
  "master_section",
  "question_card",
  "chat_exchange",
  "image",
  "latex",
]);

function safeNotebookActionBlock(value: unknown): NotebookActionBlock | null {
  const raw = record(value);
  if (!raw) return null;
  const attrs = record(raw.attrs) ?? undefined;
  const text = textValue(raw.text) ?? textValue(attrs?.text);
  const kind = nonEmptyString(raw.kind);
  if (!kind || !NOTEBOOK_ACTION_BLOCK_KINDS.has(kind as NotebookActionBlock["kind"])) {
    return {
      kind: "note",
      text: text ?? "Unsupported notebook block",
      ...(attrs ? { attrs } : {}),
    };
  }
  return {
    kind: kind as NotebookActionBlock["kind"],
    ...(attrs ? { attrs } : {}),
    ...(textValue(raw.text) ? { text: textValue(raw.text)! } : {}),
  } as NotebookActionBlock;
}

function aiBlockToHtml(block: NotebookActionBlock): string {
  // Map the action's compact block schema to the custom-element tags
  // that the TipTap parseHTML extensions recognise.
  const attrs = block.attrs ?? {};
  switch (block.kind) {
    case "note":
      return noteBlockHtml(textValue(block.text) ?? textValue(attrs.text) ?? "");
    case "claim_card": {
      const claimId = nonEmptyString(attrs.claim_id);
      if (!claimId) return fallbackNoteBlockHtml(block, "Missing claim id");
      return customElementHtml("antiek-claim-card", {
        claim_id: claimId,
        investigation_id: nonEmptyString(attrs.investigation_id),
      });
    }
    case "region_embed": {
      const documentId = nonEmptyString(attrs.document_id);
      if (!documentId) return fallbackNoteBlockHtml(block, "Missing document id");
      return customElementHtml("antiek-region-embed", {
        document_id: documentId,
        page: positiveIntegerString(attrs.page),
        caption: textValue(attrs.caption) ?? textValue(block.text),
      });
    }
    case "cross_doc_link": {
      const fromDoc = nonEmptyString(attrs.from_doc);
      const toDoc = nonEmptyString(attrs.to_doc);
      if (!fromDoc || !toDoc) {
        return fallbackNoteBlockHtml(block, "Missing cross-document ids");
      }
      return customElementHtml("antiek-cross-doc-link", {
        from_doc: fromDoc,
        to_doc: toDoc,
        bridge: textValue(attrs.bridge) ?? textValue(block.text),
      });
    }
    case "master_section": {
      const synthesisId = nonEmptyString(attrs.synthesis_id);
      if (!synthesisId) return fallbackNoteBlockHtml(block, "Missing synthesis id");
      return customElementHtml("antiek-master-section", {
        synthesis_id: synthesisId,
        section: textValue(attrs.section) ?? textValue(block.text),
      });
    }
    case "question_card": {
      const text = textValue(block.text) ?? textValue(attrs.text);
      if (!text) return fallbackNoteBlockHtml(block, "Missing question text");
      return customElementHtml("antiek-question-card", {
        parked_question_id: nonEmptyString(attrs.parked_question_id),
        text,
      });
    }
    case "chat_exchange": {
      const userText = textValue(attrs.user_text);
      const assistantText = textValue(attrs.assistant_text) ?? textValue(block.text);
      if (!userText && !assistantText) {
        return fallbackNoteBlockHtml(block, "Missing chat exchange text");
      }
      return customElementHtml("antiek-chat-exchange", {
        exchange_id: nonEmptyString(attrs.exchange_id),
        user_text: userText,
        assistant_text: assistantText,
      });
    }
    case "image": {
      const src = nonEmptyString(attrs.src);
      if (!src) return fallbackNoteBlockHtml(block, "Missing image source");
      return customElementHtml("antiek-image", {
        src,
        alt: textValue(attrs.alt),
        caption: textValue(attrs.caption) ?? textValue(block.text),
      });
    }
    case "latex": {
      const source = textValue(attrs.source) ?? textValue(block.text);
      if (!source) return fallbackNoteBlockHtml(block, "Missing LaTeX source");
      return customElementHtml("antiek-latex", { source });
    }
  }
}

function fallbackNoteBlockHtml(
  block: NotebookActionBlock,
  fallbackText: string,
): string {
  const attrs = block.attrs ?? {};
  return noteBlockHtml(
    nonEmptyString(block.text) ??
      nonEmptyString(attrs.text) ??
      nonEmptyString(attrs.caption) ??
      nonEmptyString(attrs.bridge) ??
      nonEmptyString(attrs.assistant_text) ??
      fallbackText,
  );
}

function noteBlockHtml(text: string): string {
  return customElementHtml("antiek-note", { text });
}

function customElementHtml(
  tag: string,
  attrs: Record<string, string | null | undefined>,
): string {
  const renderedAttrs = Object.entries(attrs)
    .filter((entry): entry is [string, string] => entry[1] != null)
    .map(([name, value]) => `${name}="${escapeAttr(value)}"`)
    .join(" ");
  return renderedAttrs ? `<${tag} ${renderedAttrs}></${tag}>` : `<${tag}></${tag}>`;
}

function escapeAttr(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/"/g, "&quot;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function textValue(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

function record(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function nonEmptyString(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

function positiveIntegerString(value: unknown): string | null {
  if (typeof value === "number") {
    return Number.isSafeInteger(value) && value > 0 ? String(value) : null;
  }
  const text = nonEmptyString(value);
  if (!text || !/^\d+$/.test(text)) return null;
  const n = Number(text);
  return Number.isSafeInteger(n) && n > 0 ? String(n) : null;
}

// ─── Workspace context serialisation (sent TO the assistant) ─────────

/**
 * Build a compact JSON description of the current workspace state.
 * Sent as part of the assistant's request so the model can reference
 * what's currently visible to the operator.
 *
 * Intentionally small — we ship descriptors + ids only, not panel
 * contents (the substrate already gives the model access to claims +
 * documents via dispatch). Total size targets ~1-2 KB for a typical
 * workspace.
 */
export function buildWorkspaceContext(): {
  panels: Array<{
    id: string;
    kind: string;
    mode: string;
    title: string;
    pinned: boolean;
  }>;
  focused: string | null;
  route: string;
} {
  const ws = useWorkspace.getState();
  return {
    panels: Object.values(ws.panels).map((p) => ({
      id: p.id,
      kind: p.kind,
      mode: p.mode,
      title: p.title,
      pinned: p.pinned,
    })),
    focused: ws.focusedPanelId,
    route:
      typeof window !== "undefined" ? window.location.pathname : "/",
  };
}

/**
 * The protocol description we send the model as part of the
 * system / context message. Documents:
 *   - the action schema
 *   - the rules (closed enum, idempotent ids, no shell escape)
 *   - the current workspace state
 *
 * Kept as a static string (not a stub) so the operator can audit
 * exactly what the assistant sees.
 */
export function workspaceContextPrompt(): string {
  const ctx = buildWorkspaceContext();
  return (
    `# Antiek workspace (your context window)\n\n` +
    `You are a thought-partner attached to Antiek's reading product.\n` +
    `You may, after your prose reply, append a fenced \`@@actions\` block\n` +
    `containing a JSON array of structured actions to dispatch. The\n` +
    `closed set of action kinds:\n\n` +
    `  open_panel       { panel_kind, props?, mode?, title?, id? }\n` +
    `  focus_panel      { id }\n` +
    `  close_panel      { id }\n` +
    `  set_panel_mode   { id, mode }     // docked-left / -right / -bottom / floating / popout\n` +
    `  add_to_notebook  { notebook_id, block: { kind, attrs?, text? } }\n` +
    `  chase_question   { text, investigation_id? }\n` +
    `  toast            { level: info|ok|warn|err, message }\n\n` +
    `Rules:\n` +
    `  - Anything outside the enum is silently dropped.\n` +
    `  - The operator sees every action as a clickable pill they can undo.\n` +
    `  - Stable \`id\` makes re-dispatch idempotent (focuses, not duplicates).\n` +
    `  - Prefer at most 2 actions per reply.\n\n` +
    `Workspace state right now:\n` +
    `\`\`\`json\n${JSON.stringify(ctx, null, 2)}\n\`\`\`\n`
  );
}
