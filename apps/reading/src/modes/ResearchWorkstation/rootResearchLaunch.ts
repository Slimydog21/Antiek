import type { StartInvestigationRequest } from "../../lib/api";
import type { PreparedModelLaunch } from "../../hooks/useOwnerModelController";
type ActiveLaunch = Exclude<PreparedModelLaunch, { kind: "blocked" }>;
export type RootResearchIntent = Readonly<{
  nonce: string;
  separateFrom: readonly string[] | null;
}>;
export type RootResearchLaunchHandle = Readonly<{ nonce: string }>;
interface IssuedRecord {
  request: Readonly<StartInvestigationRequest>;
  prepared: ActiveLaunch;
  status: "pending" | "unknown";
}
/** Memory-only continuity; no replay, durable owner identity or server lookup. */
export function createRootResearchLaunchArchive() {
  const unresolved = new Map<RootResearchLaunchHandle, IssuedRecord>();
  const issuedNonces = new Set<string>();
  const acceptedRecords = new Map<
    RootResearchLaunchHandle,
    Readonly<{
      origin: Readonly<{
        scope: ActiveLaunch["scope"];
        route: ActiveLaunch["kind"];
        operationId: string | null;
      }>;
      receipt: Readonly<{
        investigationId: string;
        status: string;
        startEventId: string;
      }>;
    }>
  >();
  const holdIds = () =>
    [...unresolved.keys()].map((handle) => handle.nonce).sort();
  const createIntent = (separate = false): RootResearchIntent =>
    Object.freeze({
      nonce: crypto.randomUUID(),
      separateFrom: separate ? Object.freeze(holdIds()) : null,
    });
  const canBegin = (intent: RootResearchIntent) => {
    if (issuedNonces.has(intent.nonce)) return false;
    const holds = holdIds();
    if (!holds.length) return true;
    return (
      intent.separateFrom !== null &&
      holds.length === intent.separateFrom.length &&
      holds.every((id, i) => id === intent.separateFrom?.[i])
    );
  };
  return {
    createIntent,
    canBegin,
    hasUnresolved: () => unresolved.size > 0,
    begin(
      intent: RootResearchIntent,
      request: Readonly<StartInvestigationRequest>,
      prepared: ActiveLaunch,
    ): RootResearchLaunchHandle | null {
      if (!canBegin(intent)) return null;
      const handle = Object.freeze({ nonce: intent.nonce });
      const copied = Object.freeze({
        ...request,
        ...(request.model_choice
          ? { model_choice: Object.freeze({ ...request.model_choice }) }
          : {}),
      });
      issuedNonces.add(intent.nonce);
      unresolved.set(handle, { request: copied, prepared, status: "pending" });
      return handle;
    },
    uncertain(handle: RootResearchLaunchHandle) {
      const record = unresolved.get(handle);
      if (record) record.status = "unknown";
    },
    accepted(handle: RootResearchLaunchHandle, response: unknown): boolean {
      if (
        typeof response !== "object" ||
        response === null ||
        !("investigation_id" in response) ||
        !("status" in response) ||
        !("start_event_id" in response) ||
        typeof response.investigation_id !== "string" ||
        !response.investigation_id.trim() ||
        typeof response.status !== "string" ||
        !response.status ||
        typeof response.start_event_id !== "string" ||
        !response.start_event_id
      )
        return false;
      const known = acceptedRecords.get(handle);
      if (known)
        return (
          known.receipt.investigationId === response.investigation_id &&
          known.receipt.status === response.status &&
          known.receipt.startEventId === response.start_event_id
        );
      const issued = unresolved.get(handle);
      if (!issued) return false;
      // Keep private origin and receipt strongly; discard the accepted request body.
      // This is a start receipt, never completed research or a known charge.
      acceptedRecords.set(
        handle,
        Object.freeze({
          origin: Object.freeze({
            scope: issued.prepared.scope,
            route: issued.prepared.kind,
            operationId:
              issued.prepared.kind === "saved"
                ? issued.prepared.fields.operation_id
                : null,
          }),
          receipt: Object.freeze({
            investigationId: response.investigation_id,
            status: response.status,
            startEventId: response.start_event_id,
          }),
        }),
      );
      unresolved.delete(handle);
      return true;
    },
  };
}
export const rootResearchLaunchArchive = createRootResearchLaunchArchive();
