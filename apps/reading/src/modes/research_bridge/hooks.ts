/**
 * React hooks for the research bridge. Each hook owns one network
 * operation's state machine via a discriminated union AsyncState.
 * No external state-management dependency.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import type {
  ExtractResponse, FindGapsRequest, FindGapsResponse, GapPromptPayload,
  ListPastesResponse, PasteRequest, PasteResponse, ResearchBridgeClient,
} from "./api_client";

export type AsyncState<T> =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "ok"; data: T }
  | { kind: "error"; error: Error };

function useLatestCallId() {
  const ref = useRef(0);
  return {
    next: () => ++ref.current,
    isLatest: (id: number) => ref.current === id,
  };
}

export interface UsePastesOptions {
  client: ResearchBridgeClient;
  limit?: number;
  autoLoad?: boolean;
}

export function usePastes(opts: UsePastesOptions) {
  const { client, limit = 50, autoLoad = true } = opts;
  const [state, setState] = useState<AsyncState<ListPastesResponse>>(
    autoLoad ? { kind: "loading" } : { kind: "idle" },
  );
  const guard = useLatestCallId();

  const refresh = useCallback(async () => {
    const callId = guard.next();
    setState({ kind: "loading" });
    try {
      const data = await client.listPastes({ limit });
      if (!guard.isLatest(callId)) return;
      setState({ kind: "ok", data });
    } catch (e) {
      if (!guard.isLatest(callId)) return;
      setState({ kind: "error", error: e as Error });
    }
  }, [client, limit, guard]);

  useEffect(() => {
    if (autoLoad) void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoLoad, client, limit]);

  return { state, refresh };
}

export function usePostPaste(client: ResearchBridgeClient) {
  const [state, setState] = useState<AsyncState<PasteResponse>>({ kind: "idle" });
  const guard = useLatestCallId();
  const post = useCallback(async (req: PasteRequest): Promise<PasteResponse> => {
    const callId = guard.next();
    setState({ kind: "loading" });
    try {
      const data = await client.postPaste(req);
      if (guard.isLatest(callId)) setState({ kind: "ok", data });
      return data;
    } catch (e) {
      if (guard.isLatest(callId)) setState({ kind: "error", error: e as Error });
      throw e;
    }
  }, [client, guard]);
  return { state, post };
}

export function useExtract(client: ResearchBridgeClient) {
  const [state, setState] = useState<AsyncState<ExtractResponse>>({ kind: "idle" });
  const guard = useLatestCallId();
  const extract = useCallback(
    async (documentId: string, regenerate = false): Promise<ExtractResponse> => {
      const callId = guard.next();
      setState({ kind: "loading" });
      try {
        const data = await client.postExtract(documentId, { regenerate });
        if (guard.isLatest(callId)) setState({ kind: "ok", data });
        return data;
      } catch (e) {
        if (guard.isLatest(callId)) setState({ kind: "error", error: e as Error });
        throw e;
      }
    },
    [client, guard],
  );
  return { state, extract };
}

export function useFindGaps(client: ResearchBridgeClient) {
  const [state, setState] = useState<AsyncState<FindGapsResponse>>({ kind: "idle" });
  const guard = useLatestCallId();
  const find = useCallback(async (req: FindGapsRequest): Promise<FindGapsResponse> => {
    const callId = guard.next();
    setState({ kind: "loading" });
    try {
      const data = await client.postFindGaps(req);
      if (guard.isLatest(callId)) setState({ kind: "ok", data });
      return data;
    } catch (e) {
      if (guard.isLatest(callId)) setState({ kind: "error", error: e as Error });
      throw e;
    }
  }, [client, guard]);
  const replace = useCallback((data: FindGapsResponse) => {
    setState({ kind: "ok", data });
  }, []);
  return { state, find, replace };
}

export type SignalType = "would_run" | "skip";

export function useSignals(
  client: ResearchBridgeClient,
  initial?: Record<string, SignalType>,
) {
  const [signals, setSignals] = useState<Record<string, SignalType>>(initial ?? {});
  const [errors, setErrors] = useState<Record<string, Error>>({});

  const setSignal = useCallback(
    async (promptId: string, signalType: SignalType): Promise<void> => {
      const prev = signals[promptId];
      setSignals((s) => ({ ...s, [promptId]: signalType }));
      setErrors((e) => {
        const { [promptId]: _removed, ...rest } = e;
        return rest;
      });
      try {
        await client.postSignal(promptId, signalType);
      } catch (err) {
        setSignals((s) => {
          if (prev === undefined) {
            const { [promptId]: _drop, ...rest } = s;
            return rest;
          }
          return { ...s, [promptId]: prev };
        });
        setErrors((e) => ({ ...e, [promptId]: err as Error }));
        throw err;
      }
    },
    [client, signals],
  );

  return { signals, errors, setSignal };
}

export interface PasteBackResult {
  document_id: string;
  insights_count: number;
  open_questions_count: number;
  was_new: boolean;
}

export function usePasteBack(client: ResearchBridgeClient) {
  const [state, setState] = useState<AsyncState<PasteBackResult>>({ kind: "idle" });
  const guard = useLatestCallId();

  const pasteBack = useCallback(
    async (
      prompt: GapPromptPayload,
      rawText: string,
      sessionId: string | null = null,
    ): Promise<PasteBackResult> => {
      const callId = guard.next();
      setState({ kind: "loading" });
      try {
        const paste = await client.postPaste({
          raw_text: rawText,
          source_override: prompt.target_provider,
          operator_label: `answer to: ${prompt.prompt_text.slice(0, 100)}`,
          session_id: sessionId,
        });
        await client.postAnswer(prompt.prompt_id, paste.document_id);
        const ex = await client.postExtract(paste.document_id);
        const result: PasteBackResult = {
          document_id: paste.document_id,
          insights_count: ex.insights.length,
          open_questions_count: ex.open_questions.length,
          was_new: true,
        };
        if (guard.isLatest(callId)) setState({ kind: "ok", data: result });
        return result;
      } catch (e) {
        if (guard.isLatest(callId)) setState({ kind: "error", error: e as Error });
        throw e;
      }
    },
    [client, guard],
  );

  const reset = useCallback(() => setState({ kind: "idle" }), []);
  return { state, pasteBack, reset };
}
