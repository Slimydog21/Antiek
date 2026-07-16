import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";

import SessionBrandChrome from "../../brand/SessionBrandChrome";
import TrajectoryReplay from "../../components/TrajectoryReplay";
import type { Event } from "../../generated/types";
import { API_BASE, apiFetch } from "../../lib/api";
import { PanelHost } from "../../workspace/PanelHost";

/**
 * Trajectory replay route (PostHog Wedge 5, master-spec §14.1).
 *
 * Loads the typed event log for an investigation and feeds it into
 * the existing ``TrajectoryReplay`` viewer. After the initial fetch,
 * subscribes to /ws/events?investigation_id=<id> so newly-emitted
 * events stream into the timeline live.
 *
 * Per master-spec §14.1: trajectory replay is the substrate of
 * operator-graded outcomes. Live updates let the operator grade as
 * the investigation runs rather than waiting for completion + reload.
 */
export default function Replay() {
  const { investigationId } = useParams<{ investigationId: string }>();
  const [events, setEvents] = useState<Event[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [wsConnected, setWsConnected] = useState<boolean>(false);
  const wsRef = useRef<WebSocket | null>(null);

  const reload = useCallback(async () => {
    if (!investigationId) {
      setEvents([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const resp = await apiFetch(
        `${API_BASE}/trajectory/${encodeURIComponent(investigationId)}`,
      );
      if (!resp.ok) {
        throw new Error(
          `GET /trajectory failed: HTTP ${resp.status}`,
        );
      }
      const data = await resp.json();
      const list: Event[] = (data.events ?? data) as Event[];
      setEvents(Array.isArray(list) ? list : []);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
      setEvents([]);
    } finally {
      setLoading(false);
    }
  }, [investigationId]);

  useEffect(() => {
    void reload();
  }, [reload]);

  // WebSocket live tail. In dev (API_BASE empty) the Vite proxy
  // forwards /ws/events to the FastAPI backend. In prod the API
  // lives on api.antiek.ai so we have to construct an explicit
  // cross-origin ws URL — same Set-Cookie story as apiFetch.
  useEffect(() => {
    if (!investigationId) return;

    let wsBase: string;
    if (API_BASE) {
      // Production: convert https://api.antiek.ai → wss://api.antiek.ai
      wsBase = API_BASE.replace(/^http/, "ws");
    } else {
      // Dev / same-origin: use the page origin so Vite proxy forwards.
      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      wsBase = `${protocol}//${window.location.host}`;
    }
    const url = `${wsBase}/ws/events?investigation_id=${encodeURIComponent(investigationId)}`;

    let cancelled = false;
    let ws: WebSocket | null = null;

    try {
      ws = new WebSocket(url);
    } catch {
      // Browser refused to construct (mixed-content, malformed url) —
      // degrade silently; the initial fetch still works.
      return;
    }
    wsRef.current = ws;

    ws.onopen = () => {
      if (!cancelled) setWsConnected(true);
    };
    ws.onclose = () => {
      if (!cancelled) setWsConnected(false);
    };
    ws.onerror = () => {
      if (!cancelled) setWsConnected(false);
    };
    ws.onmessage = (msg) => {
      if (cancelled) return;
      try {
        const payload = JSON.parse(msg.data);
        // Keepalive frames have `type === "ping"` — skip those.
        if (payload && payload.type === "ping") return;
        if (!payload || typeof payload !== "object") return;
        if (!payload.event_id) return;
        setEvents((prev) => {
          // Skip if we've already seen this event (re-subscribe races).
          if (prev.some((e) => e.event_id === payload.event_id)) {
            return prev;
          }
          return [...prev, payload as Event];
        });
      } catch {
        // Malformed frame — drop. Live tail is best-effort.
      }
    };

    return () => {
      cancelled = true;
      try {
        ws?.close();
      } catch {
        // already closed
      }
      wsRef.current = null;
    };
  }, [investigationId]);

  // S10 row 10.14 — Replay wraps the main trajectory view in
  // PanelHost with the step-list panel docked-left.
  const starters = investigationId
    ? [
        {
          kind: "ReplayStepList" as const,
          mode: "docked-left" as const,
          title: "Steps",
          id: `replay:${investigationId}:steps`,
          props: { investigationId },
        },
      ]
    : [];

  return (
    <PanelHost starters={starters}>
      <main className="h-full overflow-y-auto bg-ice-0 dark:bg-charcoal-2">
        <div className="max-w-5xl mx-auto px-8 py-10 space-y-6">
          <SessionBrandChrome
            testIdPrefix="replay-home"
            title="Trajectory replay"
          >
            <p className="text-sm text-ink-soft dark:text-starlight leading-relaxed">
              Re-read this investigation event-by-event. Per master-spec
              §14.1: replay is the substrate of operator-graded
              outcomes — replay first, grade second.
            </p>
            <p className="text-xs font-mono text-shadow-1 dark:text-moonlight flex items-center gap-2">
              <span>investigation_id = {investigationId ?? "—"}</span>
              <span
                className={`px-1.5 py-0.5 rounded ${
                  wsConnected
                    ? "bg-emerald-100 text-emerald-700"
                    : "bg-ice-3 dark:bg-charcoal-1 text-shadow-1 dark:text-moonlight"
                }`}
              >
                {wsConnected ? "live" : "offline"}
              </span>
              <span>· {events.length} events</span>
            </p>
          </SessionBrandChrome>

          {loading && (
            <p className="text-sm text-shadow-1 dark:text-moonlight italic">Loading trajectory…</p>
          )}
          {error && (
            <p className="text-sm text-emperor border border-red-200 bg-red-50 px-3 py-2 rounded">
              {error}
            </p>
          )}
          {!loading && !error && events.length === 0 && (
            <p className="text-sm text-shadow-1 dark:text-moonlight italic">
              No events recorded for this investigation yet. The live
              tail will populate as events arrive.
            </p>
          )}
          {events.length > 0 && (
            <TrajectoryReplay events={events} />
          )}
        </div>
      </main>
    </PanelHost>
  );
}
