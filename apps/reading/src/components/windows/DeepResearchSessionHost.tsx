import { SpawnMergePanel } from "../engagement/SpawnMergePanel";
import { TwinNotesPanel } from "../engagement/TwinNotesPanel";
import { useInWindow } from "./windowHostContext";

export type DeepResearchSessionHostProps = {
  session_id?: string;
  spawn_id?: string;
  investigation_id?: string;
  parent_asset_id?: string;
  selection_text?: string;
  status?: string;
  view_format?: string;
  goal?: string;
};

function Row({ label, value }: { label: string; value: string }) {
  return <div><dt className="text-xs uppercase text-shadow-1">{label}</dt>
    <dd className="break-words text-sm text-ink dark:text-parchment">{value}</dd></div>;
}

export default function DeepResearchSessionHost(props: DeepResearchSessionHostProps) {
  useInWindow();
  const parent = props.parent_asset_id?.trim();
  const spawn = props.spawn_id?.trim();
  const viewFormat = (props.view_format?.trim() || "html").toLowerCase();
  return (
    <div className="flex h-full flex-col gap-4 overflow-auto bg-transparent p-6"
      data-testid="deep-research-session-host" data-view-format={viewFormat}>
      <header>
        <h1 className="font-serif text-lg text-ink dark:text-parchment">Deep research session</h1>
        <p className="text-xs text-shadow-1">Floating HTML research linked to the reader.</p>
      </header>
      <dl className="grid gap-3">
        <Row label="Session" value={props.session_id?.trim() || "(missing session)"} />
        <Row label="Spawn" value={spawn || "(missing spawn)"} />
        <Row label="Parent asset" value={parent || "(missing parent)"} />
        <Row label="Status" value={props.status?.trim() || "unknown"} />
        {props.investigation_id ? <Row label="Investigation" value={props.investigation_id} /> : null}
        {props.goal ? <Row label="Goal" value={props.goal} /> : null}
      </dl>
      <section className="border-t border-black/10 pt-4 dark:border-white/10">
        <h2 className="text-xs uppercase text-shadow-1">Selection</h2>
        <p className="whitespace-pre-wrap text-sm" data-testid="deep-research-selection">
          {props.selection_text?.trim() || "(no selection)"}
        </p>
      </section>
      {parent ? <TwinNotesPanel assetId={parent} spawnId={spawn || null} /> : null}
      {parent && spawn ? <SpawnMergePanel parentAssetId={parent} spawnId={spawn} /> : null}
    </div>
  );
}
