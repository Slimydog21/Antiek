import ChaseThread from "../../modes/ResearchWorkstation/ChaseThread";

/**
 * Runtime boundary between the opaque window payload registry and
 * ChaseThread's required research context. Window identity is presentation
 * only; malformed payloads fail closed and never reach the launch authority.
 */
export default function ResearchChaseWindow(props: Record<string, unknown>) {
  const spawnContext = props.spawnContext;
  const parentInvestigationId = props.parentInvestigationId;
  const reservedChildId = props.reservedChildId;
  if (
    typeof spawnContext !== "string" ||
    spawnContext.trim().length === 0 ||
    typeof parentInvestigationId !== "string" ||
    parentInvestigationId.trim().length === 0 ||
    parentInvestigationId.trim() !== parentInvestigationId ||
    (reservedChildId !== undefined &&
      (typeof reservedChildId !== "string" ||
        reservedChildId.trim().length === 0 ||
        reservedChildId.trim() !== reservedChildId))
  ) {
    return (
      <div role="alert" className="p-4 font-serif text-sm text-emperor">
        This research thread has an invalid source passage or research context.
      </div>
    );
  }
  return (
    <ChaseThread
      spawnContext={spawnContext}
      parentInvestigationId={parentInvestigationId}
      reservedChildId={typeof reservedChildId === "string" ? reservedChildId : undefined}
    />
  );
}
