import { useCallback, useState } from "react";

/**
 * Reply-mode preference (Read SPR-07): does the reader want AI replies in
 * the conversational rabbit hole as text (read it) or audio (hear it)?
 * Persisted to localStorage so the choice sticks across sessions. Text is
 * the default — voice is opt-in, and the text is always shown regardless,
 * so this only governs whether replies auto-speak.
 */

export type ReplyMode = "text" | "audio";

const KEY = "antiek.read.reply_mode";

function read(): ReplyMode {
  try {
    return window.localStorage.getItem(KEY) === "audio" ? "audio" : "text";
  } catch {
    return "text";
  }
}

export function useReplyMode(): { mode: ReplyMode; setMode: (m: ReplyMode) => void } {
  const [mode, setModeState] = useState<ReplyMode>(read);

  const setMode = useCallback((m: ReplyMode) => {
    setModeState(m);
    try {
      window.localStorage.setItem(KEY, m);
    } catch {
      /* localStorage unavailable — preference is in-memory for this session */
    }
  }, []);

  return { mode, setMode };
}
