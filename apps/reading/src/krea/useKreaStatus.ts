import { useEffect, useRef, useState } from "react";

import { getKreaStatus, type KreaStatusSnapshot } from "../api/krea";

export type KreaStatusHookState =
  | { status: "loading"; data: null; error: null }
  | { status: "ready"; data: KreaStatusSnapshot; error: null }
  | { status: "error"; data: null; error: string };

export type KreaStatusFetcher = () => Promise<KreaStatusSnapshot>;

export function useKreaStatus(
  fetchStatus: KreaStatusFetcher = getKreaStatus,
): KreaStatusHookState {
  const [state, setState] = useState<KreaStatusHookState>({
    status: "loading",
    data: null,
    error: null,
  });
  const reqId = useRef(0);

  useEffect(() => {
    const myId = ++reqId.current;
    let cancelled = false;
    setState({ status: "loading", data: null, error: null });
    fetchStatus()
      .then((data) => {
        if (cancelled || myId !== reqId.current) return;
        setState({ status: "ready", data, error: null });
      })
      .catch((e: unknown) => {
        if (cancelled || myId !== reqId.current) return;
        const error = e instanceof Error && e.message ? e.message : "offline";
        setState({ status: "error", data: null, error });
      });
    return () => {
      cancelled = true;
    };
  }, [fetchStatus]);

  return state;
}
