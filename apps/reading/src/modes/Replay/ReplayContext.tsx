import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import type { Event } from "../../generated/types";
import { API_BASE, apiFetch } from "../../lib/api";

export type ReplayAuthority = {
  events: Event[];
  loading: boolean;
  error: string | null;
  connected: boolean;
};

const ReplayContext = createContext<ReplayAuthority>({
  events: [],
  loading: false,
  error: null,
  connected: false,
});

export const REPLAY_UNAVAILABLE = "The replay could not be loaded. Try again in a moment.";

export function useReplay(): ReplayAuthority {
  return useContext(ReplayContext);
}

type Props = {
  investigationId?: string;
  executionEnabled?: boolean;
  initialEvents?: Event[];
  initialLoading?: boolean;
  initialError?: boolean;
  initialConnected?: boolean;
  children: ReactNode;
};

/** The route's single fetch + live-tail authority, shared through PanelHost. */
export function ReplayProvider({
  investigationId,
  executionEnabled = true,
  initialEvents = [],
  initialLoading,
  initialError = false,
  initialConnected = false,
  children,
}: Props) {
  const [events, setEvents] = useState<Event[]>(initialEvents);
  const [loading, setLoading] = useState(initialLoading ?? executionEnabled);
  const [error, setError] = useState<string | null>(
    initialError ? REPLAY_UNAVAILABLE : null,
  );
  const [connected, setConnected] = useState(initialConnected);

  useEffect(() => {
    if (!executionEnabled) return;
    if (!investigationId) {
      setEvents([]);
      setLoading(false);
      setConnected(false);
      return;
    }

    let cancelled = false;
    // A route change is a new authority boundary. Never let the previous
    // investigation's events or connection badge bleed into this one.
    setEvents([]);
    setLoading(true);
    setError(null);
    setConnected(false);
    void apiFetch(`${API_BASE}/trajectory/${encodeURIComponent(investigationId)}`)
      .then(async (response) => {
        if (!response.ok) throw new Error("trajectory unavailable");
        const data = await response.json();
        const list = (data.events ?? data) as Event[];
        if (!cancelled) {
          const history = Array.isArray(list) ? list : [];
          setEvents((liveEvents) => {
            const historyIds = new Set(history.map((event) => event.event_id));
            return [...history, ...liveEvents.filter((event) => !historyIds.has(event.event_id))];
          });
        }
      })
      .catch(() => {
        if (!cancelled) {
          setEvents([]);
          setError(REPLAY_UNAVAILABLE);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    let wsBase: string;
    if (API_BASE) {
      wsBase = API_BASE.replace(/^http/, "ws");
    } else {
      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      wsBase = `${protocol}//${window.location.host}`;
    }
    const url = `${wsBase}/ws/events?investigation_id=${encodeURIComponent(investigationId)}`;
    let socket: WebSocket | null = null;
    try {
      socket = new WebSocket(url);
      socket.onopen = () => !cancelled && setConnected(true);
      socket.onclose = () => !cancelled && setConnected(false);
      socket.onerror = () => !cancelled && setConnected(false);
      socket.onmessage = (message) => {
        if (cancelled) return;
        try {
          const payload = JSON.parse(message.data);
          if (payload?.type === "ping" || !payload || typeof payload !== "object" || !payload.event_id) return;
          setEvents((previous) =>
            previous.some((event) => event.event_id === payload.event_id)
              ? previous
              : [...previous, payload as Event],
          );
        } catch {
          // Malformed live-tail frames are intentionally ignored.
        }
      };
    } catch {
      // Initial HTTP history remains useful when a socket cannot be created.
    }

    return () => {
      cancelled = true;
      try {
        socket?.close();
      } catch {
        // The socket may already be closed.
      }
    };
  }, [executionEnabled, investigationId]);

  const value = useMemo(
    () => ({ events, loading, error, connected }),
    [connected, error, events, loading],
  );
  return <ReplayContext.Provider value={value}>{children}</ReplayContext.Provider>;
}
