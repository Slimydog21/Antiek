/**
 * Multi-turn Thought Partner thread (Surface E / AISidecar).
 *
 * Mirrors TalkToBook's useTalkThread pattern: sessionStorage, not DuckDB.
 * Scoped by open reading document when SERVABLE reading mount is active,
 * else "__workspace__" so BrainstormStation + Cmd+/ share one workspace thread.
 * Cite: TalkToBook SPR-08 M2; dual structure — /thought-partner stays library-
 * wide; history is prompt context only.
 */
import { useCallback, useEffect, useState } from "react";

import { getReadingFocus, READING_FOCUS_EVENT } from "../lib/readingFocus";

export type ThoughtPartnerShape = "CHALLENGE" | "SYNTHESIS" | "EXTENSION";

export interface ThoughtPartnerMessage {
  id: string;
  question: string;
  /** Null while the turn is in flight. */
  answer: string | null;
  shape: ThoughtPartnerShape | null;
}

const MAX_HISTORY_TURNS = 8;
const KEY_PREFIX = "antiek.tp.thread.v1.";

function scopeKey(): string {
  const doc = getReadingFocus()?.documentId?.trim();
  return KEY_PREFIX + (doc || "__workspace__");
}

function empty(): ThoughtPartnerMessage[] {
  return [];
}

function readStored(key: string): ThoughtPartnerMessage[] {
  try {
    const raw = window.sessionStorage.getItem(key);
    if (!raw) return empty();
    const parsed = JSON.parse(raw) as ThoughtPartnerMessage[];
    return Array.isArray(parsed) ? parsed : empty();
  } catch {
    return empty();
  }
}

function writeStored(key: string, messages: ThoughtPartnerMessage[]): void {
  try {
    window.sessionStorage.setItem(key, JSON.stringify(messages));
  } catch {
    /* private mode — in-memory still works */
  }
}

function genId(): string {
  const rand =
    typeof crypto !== "undefined" && crypto.randomUUID
      ? crypto.randomUUID().slice(0, 8)
      : Math.random().toString(36).slice(2, 10);
  return `tp-${rand}`;
}

export function normalizeThoughtPartnerShape(raw: unknown): ThoughtPartnerShape {
  const s = String(raw ?? "SYNTHESIS").toUpperCase();
  if (s === "CHALLENGE" || s === "EXTENSION") return s;
  return "SYNTHESIS";
}

/** Prior completed turns for POST /thought-partner history (bounded). */
export function historyPayload(
  messages: ThoughtPartnerMessage[],
): Array<{ question: string; answer: string }> {
  const done = messages.filter(
    (m) => typeof m.answer === "string" && m.answer.trim().length > 0,
  );
  return done.slice(-MAX_HISTORY_TURNS).map((m) => ({
    question: m.question,
    answer: m.answer as string,
  }));
}

export interface UseThoughtPartnerThread {
  messages: ThoughtPartnerMessage[];
  scope: string;
  startTurn: (question: string) => string;
  completeTurn: (
    messageId: string,
    answer: string,
    shape: ThoughtPartnerShape | string,
  ) => void;
  failTurn: (messageId: string, errorText: string) => void;
  clear: () => void;
}

export function useThoughtPartnerThread(): UseThoughtPartnerThread {
  const [scope, setScope] = useState(() => scopeKey());
  const [messages, setMessages] = useState<ThoughtPartnerMessage[]>(() =>
    readStored(scopeKey()),
  );

  useEffect(() => {
    const sync = () => {
      const next = scopeKey();
      setScope((prev) => {
        if (prev === next) return prev;
        setMessages(readStored(next));
        return next;
      });
    };
    sync();
    window.addEventListener(READING_FOCUS_EVENT, sync);
    return () => window.removeEventListener(READING_FOCUS_EVENT, sync);
  }, []);

  const startTurn = useCallback(
    (question: string) => {
      const id = genId();
      setMessages((prev) => {
        const next = [
          ...prev,
          { id, question, answer: null, shape: null },
        ];
        writeStored(scope, next);
        return next;
      });
      return id;
    },
    [scope],
  );

  const completeTurn = useCallback(
    (
      messageId: string,
      answer: string,
      shape: ThoughtPartnerShape | string,
    ) => {
      setMessages((prev) => {
        const next = prev.map((m) =>
          m.id === messageId
            ? {
                ...m,
                answer,
                shape: normalizeThoughtPartnerShape(shape),
              }
            : m,
        );
        writeStored(scope, next);
        return next;
      });
    },
    [scope],
  );

  const failTurn = useCallback(
    (messageId: string, errorText: string) => {
      setMessages((prev) => {
        const next = prev.map((m) =>
          m.id === messageId
            ? {
                ...m,
                answer: errorText,
                shape: "CHALLENGE" as const,
              }
            : m,
        );
        writeStored(scope, next);
        return next;
      });
    },
    [scope],
  );

  const clear = useCallback(() => {
    setMessages(() => {
      writeStored(scope, []);
      return [];
    });
  }, [scope]);

  return { messages, scope, startTurn, completeTurn, failTurn, clear };
}
