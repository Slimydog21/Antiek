import { useCallback, useEffect, useState } from "react";

import { getHealth } from "../lib/api";

/**
 * useProviderKeys — honest activation boundary for agentic paths (SPR-08 M5).
 *
 * Reads ``registered_providers`` from ``GET /health``. An empty list means the
 * dispatch router has no live provider adapters — the Enter-to-escalate research
 * path is INERT until activation SPR-03 flips keys. Local corpus search is
 * unaffected (it never consults this hook).
 */
export type ProviderKeysState =
  | { status: "loading" }
  | { status: "ready"; providers: string[] }
  | { status: "absent" }
  | { status: "error" };

export function useProviderKeys(): ProviderKeysState & { refresh: () => void } {
  const [state, setState] = useState<ProviderKeysState>({ status: "loading" });

  const refresh = useCallback(() => {
    setState({ status: "loading" });
    void getHealth()
      .then((h) => {
        const providers = h.registered_providers ?? [];
        setState(
          providers.length > 0
            ? { status: "ready", providers }
            : { status: "absent" },
        );
      })
      .catch(() => setState({ status: "error" }));
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { ...state, refresh };
}