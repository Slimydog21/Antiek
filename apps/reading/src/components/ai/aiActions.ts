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
  undo: (() => void) | null;
  /** Timestamp for ordering / display. */
  at: number;
};

/** Execute a single parsed action. Returns a DispatchedAction record. */
export function dispatchAiAction(action: AiAction): DispatchedAction {
  const ws = useWorkspace.getState();
  const at = Date.now();

  switch (action.kind) {
    case "open_panel": {
      // Idempotent — re-firing the same action focuses the existing panel.
      const id =
        action.id ??
        `ai:${action.panel_kind}:${JSON.stringify(action.props ?? {})}`;
      const wasOpen = Boolean(ws.panels[id]);
      ws.open(
        action.panel_kind,
        (action.props ?? {}) as Record<string, unknown>,
        {
          id,
          mode: action.mode ?? "floating",
          title: action.title,
        },
      );
      return {
        action,
        label: `🪟 Opened ${action.panel_kind}${
          action.title ? " · " + action.title : ""
        }`,
        undo: wasOpen ? null : () => useWorkspace.getState().close(id),
        at,
      };
    }

    case "focus_panel": {
      ws.focus(action.id);
      return { action, label: `🎯 Focused ${action.id}`, undo: null, at };
    }

    case "close_panel": {
      const existing = ws.panels[action.id];
      ws.close(action.id);
      return {
        action,
        label: `❌ Closed ${action.id}`,
        // Best-effort undo: reopen at the previous descriptor.
        undo: existing
          ? () =>
              useWorkspace.getState().open(existing.kind, existing.props, {
                id: existing.id,
                mode: existing.mode,
                title: existing.title,
              })
          : null,
        at,
      };
    }

    case "set_panel_mode": {
      const before = ws.panels[action.id]?.mode;
      ws.setMode(action.id, action.mode);
      return {
        action,
        label: `↔ ${action.id} → ${action.mode}`,
        undo: before
          ? () => useWorkspace.getState().setMode(action.id, before)
          : null,
        at,
      };
    }

    case "add_to_notebook": {
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
      const html = aiBlockToHtml(action.block);
      const lsKey = "antiek.notebook." + action.notebook_id;
      const etagKey = lsKey + ".etag";
      try {
        const existing = window.localStorage.getItem(lsKey) ?? "<p></p>";
        const current = window.localStorage.getItem(etagKey);
        const next = (current === null ? 0 : parseInt(current, 10) || 0) + 1;
        const appended = existing.replace(
          /<\/body>\s*$/,
          "",
        ) + "\n" + html;
        window.localStorage.setItem(lsKey, appended);
        window.localStorage.setItem(etagKey, String(next));
        // Same-tab signal: editors keyed by `notebook_id` reload.
        window.dispatchEvent(
          new CustomEvent("antiek:notebook:appended", {
            detail: { notebookId: action.notebook_id, etag: next },
          }),
        );
      } catch {
        // ignore quota; the operator sees the action label without effect
      }
      return {
        action,
        label: `📓 Added a ${action.block.kind} to “${action.notebook_id}”`,
        // Undo not implemented — TipTap-aware undo would need to
        // surgically remove the appended fragment; the operator can
        // delete the block from the notebook directly.
        undo: null,
        at,
      };
    }

    case "chase_question": {
      ws.open(
        "Chase",
        {
          question: action.text,
          investigationId: action.investigation_id,
        },
        {
          id: `chase:${action.text.slice(0, 32)}`,
          mode: "floating",
          title: "Chase",
        },
      );
      return {
        action,
        label: `🔍 Chasing: “${action.text.slice(0, 48)}${
          action.text.length > 48 ? "…" : ""
        }”`,
        undo: () =>
          useWorkspace
            .getState()
            .close(`chase:${action.text.slice(0, 32)}`),
        at,
      };
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

function aiBlockToHtml(block: AiAction extends infer A
  ? A extends { kind: "add_to_notebook"; block: infer B }
    ? B
    : never
  : never): string {
  // Map the action's compact block schema to the custom-element tags
  // that the TipTap parseHTML extensions recognise.
  const escape = (s: string) =>
    s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  const attrs = block.attrs ?? {};
  switch (block.kind) {
    case "note":
      return `<antiek-note text="${escape(
        block.text ?? (attrs.text as string) ?? "",
      )}"></antiek-note>`;
    case "claim_card":
      return `<antiek-claim-card claim_id="${escape(
        (attrs.claim_id as string) ?? "",
      )}" investigation_id="${escape(
        (attrs.investigation_id as string) ?? "",
      )}"></antiek-claim-card>`;
    case "region_embed":
      return `<antiek-region-embed document_id="${escape(
        (attrs.document_id as string) ?? "",
      )}" page="${
        (attrs.page as number) ?? ""
      }" caption="${escape(
        (attrs.caption as string) ?? block.text ?? "",
      )}"></antiek-region-embed>`;
    case "cross_doc_link":
      return `<antiek-cross-doc-link from_doc="${escape(
        (attrs.from_doc as string) ?? "",
      )}" to_doc="${escape(
        (attrs.to_doc as string) ?? "",
      )}" bridge="${escape(
        (attrs.bridge as string) ?? block.text ?? "",
      )}"></antiek-cross-doc-link>`;
    case "master_section":
      return `<antiek-master-section synthesis_id="${escape(
        (attrs.synthesis_id as string) ?? "",
      )}" section="${escape(
        (attrs.section as string) ?? block.text ?? "",
      )}"></antiek-master-section>`;
    case "question_card":
      return `<antiek-question-card parked_question_id="${escape(
        (attrs.parked_question_id as string) ?? "",
      )}" text="${escape(
        block.text ?? (attrs.text as string) ?? "",
      )}"></antiek-question-card>`;
    case "chat_exchange":
      return `<antiek-chat-exchange exchange_id="${escape(
        (attrs.exchange_id as string) ?? "",
      )}" user_text="${escape(
        (attrs.user_text as string) ?? "",
      )}" assistant_text="${escape(
        (attrs.assistant_text as string) ?? block.text ?? "",
      )}"></antiek-chat-exchange>`;
    case "image":
      return `<antiek-image src="${escape(
        (attrs.src as string) ?? "",
      )}" alt="${escape(
        (attrs.alt as string) ?? "",
      )}" caption="${escape(
        (attrs.caption as string) ?? block.text ?? "",
      )}"></antiek-image>`;
    case "latex":
      return `<antiek-latex source="${escape(
        (attrs.source as string) ?? block.text ?? "",
      )}"></antiek-latex>`;
  }
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
