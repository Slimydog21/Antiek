import type { StartInvestigationRequest } from "../../lib/api";
import type { PreparedModelLaunch } from "../../hooks/useOwnerModelController";
import type { ReadyModelScope } from "../../lib/modelExecutionScope";
type ActiveLaunch = Exclude<PreparedModelLaunch, { kind: "blocked" }>;
export type RootResearchIntent = Readonly<{
  nonce: string;
  separateFrom: readonly string[] | null;
}>;
export type RootResearchLaunchHandle = Readonly<{ nonce: string }>;
type IssuedOrigin =
  | Readonly<{ kind: "root"; prepared: ActiveLaunch }>
  | Readonly<{ kind: "child"; scope: ReadyModelScope }>;
type AcceptedOrigin =
  | Readonly<{
      kind: "root";
      scope: ReadyModelScope;
      route: ActiveLaunch["kind"];
      operationId: string | null;
    }>
  | Readonly<{ kind: "child"; scope: ReadyModelScope }>;
interface IssuedRecord {
  request: Readonly<StartInvestigationRequest>;
  origin: IssuedOrigin;
  status: "pending" | "unknown";
}
/** Memory-only continuity; no replay, durable owner identity or server lookup. */
export function createRootResearchLaunchArchive() {
  const unresolved = new Map<RootResearchLaunchHandle, IssuedRecord>();
  const issuedNonces = new Set<string>();
  const acceptedRecords = new Map<
    RootResearchLaunchHandle,
    Readonly<{
      origin: AcceptedOrigin;
      receipt: Readonly<{
        investigationId: string;
        status: string;
        startEventId: string;
      }>;
    }>
  >();
  let version = 0;
  const listeners = new Set<() => void>();
  const publish = () => {
    version += 1;
    listeners.forEach((listener) => listener());
  };
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
  const issue = (
    intent: RootResearchIntent,
    request: Readonly<StartInvestigationRequest>,
    origin: IssuedOrigin,
  ): RootResearchLaunchHandle | null => {
    if (!canBegin(intent)) return null;
    const handle = Object.freeze({ nonce: intent.nonce });
    const copied = Object.freeze({
      ...request,
      ...(request.model_choice
        ? { model_choice: Object.freeze({ ...request.model_choice }) }
        : {}),
    });
    issuedNonces.add(intent.nonce);
    unresolved.set(handle, { request: copied, origin, status: "pending" });
    publish();
    return handle;
  };
  return {
    createIntent,
    canBegin,
    hasUnresolved: () => unresolved.size > 0,
    getVersion: () => version,
    subscribe(listener: () => void) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    begin(
      intent: RootResearchIntent,
      request: Readonly<StartInvestigationRequest>,
      prepared: ActiveLaunch,
    ): RootResearchLaunchHandle | null {
      return issue(intent, request, Object.freeze({ kind: "root", prepared }));
    },
    beginChild(
      intent: RootResearchIntent,
      request: Readonly<
        Pick<
          StartInvestigationRequest,
          "question" | "parent_investigation_id" | "spawn_context"
        >
      >,
      scope: ReadyModelScope,
    ): RootResearchLaunchHandle | null {
      return issue(intent, request, Object.freeze({ kind: "child", scope }));
    },
    uncertain(handle: RootResearchLaunchHandle) {
      const record = unresolved.get(handle);
      if (record && record.status !== "unknown") {
        record.status = "unknown";
        publish();
      }
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
        !response.status.trim() ||
        typeof response.start_event_id !== "string" ||
        !response.start_event_id.trim()
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
      const origin: AcceptedOrigin =
        issued.origin.kind === "child"
          ? issued.origin
          : Object.freeze({
              kind: "root",
              scope: issued.origin.prepared.scope,
              route: issued.origin.prepared.kind,
              operationId:
                issued.origin.prepared.kind === "saved"
                  ? issued.origin.prepared.fields.operation_id
                  : null,
            });
      // Keep private origin and receipt strongly; discard the accepted request body.
      // This is a start receipt, never completed research or a known charge.
      acceptedRecords.set(
        handle,
        Object.freeze({
          origin,
          receipt: Object.freeze({
            investigationId: response.investigation_id,
            status: response.status,
            startEventId: response.start_event_id,
          }),
        }),
      );
      unresolved.delete(handle);
      publish();
      return true;
    },
  };
}
export const rootResearchLaunchArchive = createRootResearchLaunchArchive();
