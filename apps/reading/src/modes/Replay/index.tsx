import { useParams } from "react-router-dom";

import TrajectoryReplay from "../../components/TrajectoryReplay";
import type { Event } from "../../generated/types";
import environmentUrl from "../../brand/werner/replay/investigation_replay_observatory_environment_v1.webp";
import { PanelHost } from "../../workspace/PanelHost";
import { ReplayProvider, useReplay } from "./ReplayContext";
import "./investigation-replay-observatory.css";

export type ReplayProps = {
  investigationId?: string;
  executionEnabled?: boolean;
  initialEvents?: Event[];
  initialLoading?: boolean;
  initialError?: boolean;
  initialConnected?: boolean;
};

export default function Replay(props: ReplayProps) {
  const params = useParams<{ investigationId: string }>();
  const investigationId = props.investigationId ?? params.investigationId;
  const starters = investigationId ? [{
    kind: "ReplayStepList" as const,
    mode: "docked-left" as const,
    title: "Signal stops",
    id: `replay:${investigationId}:steps`,
    props: { investigationId },
  }] : [];

  return (
    <ReplayProvider {...props} investigationId={investigationId}>
      <PanelHost starters={starters}>
        <ReplayObservatory investigationId={investigationId} />
      </PanelHost>
    </ReplayProvider>
  );
}

function ReplayObservatory({ investigationId }: { investigationId?: string }) {
  const { events, loading, error, connected } = useReplay();
  return (
    <main className="replay-observatory">
      <img className="replay-observatory__environment" src={environmentUrl} alt="" aria-hidden="true" draggable={false} />
      <div className="replay-observatory__wash" aria-hidden="true" />
      <div className="replay-observatory__content">
        <header className="replay-hero">
          <div>
            <p className="replay-eyebrow">Investigation replay · field observatory</p>
            <h1>Return to the trail of thought.</h1>
            <p className="replay-hero__lede">Move through the recorded trajectory, inspect what each event carried, and recover the investigation’s shape without judging its outcome.</p>
          </div>
          <div className="replay-telemetry" aria-label="Replay status">
            <span className={connected ? "is-live" : ""}><i aria-hidden="true" />{connected ? "Live tail" : "Saved history"}</span>
            <span>{events.length} events</span>
          </div>
        </header>

        <section className="replay-console" aria-labelledby="replay-console-heading">
          <div className="replay-console__mast">
            <div><p className="replay-eyebrow">Trajectory instrument</p><h2 id="replay-console-heading">Event telescope</h2></div>
            <code title={investigationId}>ID {investigationId ?? "not available"}</code>
          </div>
          {loading && <p className="replay-state" role="status">Loading the recorded trajectory…</p>}
          {error && <p className="replay-state replay-state--error" role="alert">{error}</p>}
          {!loading && !error && events.length === 0 && <p className="replay-state">No events have been recorded yet. A live event will appear here when it arrives.</p>}
          {!error && events.length > 0 && <TrajectoryReplay events={events} />}
        </section>
        <footer className="replay-boundary"><strong>Replay is observation.</strong> This surface preserves and navigates recorded events; it does not grade, rank, or rewrite the investigation.</footer>
      </div>
    </main>
  );
}
