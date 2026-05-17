import { useEffect, useRef, useState } from "react";

import type { Event } from "../generated/types";

interface UseEventStreamState {
  events: Event[];
  status: "connecting" | "open" | "closed" | "error";
  reconnects: number;
}

interface PingFrame {
  type: "ping";
}

function isPingFrame(frame: unknown): frame is PingFrame {
  return (
    typeof frame === "object" &&
    frame !== null &&
    (frame as { type?: unknown }).type === "ping"
  );
}

/**
 * Subscribe to the substrate event WebSocket for a given investigation.
 *
 * Pass null to disconnect. The hook reconnects on transient errors with
 * a 1s → 2s → 4s backoff (capped at 8s); cleanly closes on unmount and
 * when ``investigationId`` changes.
 *
 * Server-side ``ping`` keepalive frames are silently dropped — the
 * event log is the source of truth, and the ping is purely a TCP-level
 * liveness probe.
 */
export function useEventStream(
  investigationId: string | null,
): UseEventStreamState {
  const [state, setState] = useState<UseEventStreamState>({
    events: [],
    status: "closed",
    reconnects: 0,
  });
  const wsRef = useRef<WebSocket | null>(null);
  const cancelledRef = useRef(false);

  useEffect(() => {
    if (!investigationId) {
      setState({ events: [], status: "closed", reconnects: 0 });
      return;
    }
    cancelledRef.current = false;
    let attempts = 0;

    const connect = () => {
      if (cancelledRef.current) return;
      setState((s) => ({ ...s, status: "connecting" }));

      // Vite proxies /ws to ws://localhost:8000 in dev; in production
      // the Pages-hosted app needs to hit the substrate's WS at the
      // API origin (api.antiek.ai), not the Pages origin.
      //
      // VITE_API_BASE_URL is the production HTTP base (e.g.
      // "https://api.antiek.ai"); derive ws/wss from it. Falls back to
      // same-origin when unset (dev).
      const apiBase = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "";
      let wsBase: string;
      if (apiBase) {
        wsBase = apiBase.replace(/^http(s?):/i, (_m, s) => `ws${s}:`);
      } else {
        const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
        wsBase = `${proto}//${window.location.host}`;
      }
      const url = `${wsBase}/ws/events?investigation_id=${encodeURIComponent(investigationId)}`;
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        attempts = 0;
        setState((s) => ({ ...s, status: "open" }));
      };

      ws.onmessage = (e) => {
        try {
          const frame: unknown = JSON.parse(e.data);
          if (isPingFrame(frame)) return;
          setState((s) => ({ ...s, events: [...s.events, frame as Event] }));
        } catch (err) {
          // Malformed frame — drop with a console warning rather than
          // crash the subscription. The trajectory store is authoritative.
          console.warn("dropping malformed WS frame:", err, e.data);
        }
      };

      ws.onerror = () => {
        setState((s) => ({ ...s, status: "error" }));
      };

      ws.onclose = () => {
        if (cancelledRef.current) return;
        setState((s) => ({ ...s, status: "closed" }));
        attempts += 1;
        const delay = Math.min(8_000, 1_000 * 2 ** (attempts - 1));
        window.setTimeout(() => {
          if (!cancelledRef.current) {
            setState((s) => ({ ...s, reconnects: s.reconnects + 1 }));
            connect();
          }
        }, delay);
      };
    };

    connect();

    return () => {
      cancelledRef.current = true;
      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
        wsRef.current.close();
      }
      wsRef.current = null;
    };
  }, [investigationId]);

  return state;
}
