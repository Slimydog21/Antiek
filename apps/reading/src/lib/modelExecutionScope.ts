import type { AuthIdentity } from "./auth";
export type SuspensionReason =
  | "checking_identity"
  | "logout_pending"
  | "logout_failed"
  | "no_identity"
  | "unavailable"
  | "invalid_model_identity"
  | "unmounted";
export type ReadyModelScope = Readonly<{
  kind: "ready";
  epoch: number;
  identity: Readonly<AuthIdentity>;
}>;
export type ModelExecutionScope =
  | ReadyModelScope
  | Readonly<{ kind: "suspended"; epoch: number; reason: SuspensionReason }>;
export interface ModelExecutionLifecycle {
  readonly current: ModelExecutionScope;
  readCurrent(): ModelExecutionScope;
  isCurrent(scope: ReadyModelScope): boolean;
}
// Mirrors account_memory_identity.py limits and session method; no owner derivation.
const SESSION_AUTH_METHOD = "antiek_session_cookie";
const MAX_OWNER_LENGTH = 256;
const MAX_EMAIL_LENGTH = 320;

/** Admission observation only; canonical ownership remains server-defined. */
export function parseModelIdentity(
  value: unknown,
): Readonly<AuthIdentity> | null {
  if (typeof value !== "object" || value === null || Array.isArray(value))
    return null;
  if (!("user_id" in value) || !("email" in value) || !("auth_method" in value))
    return null;
  const { user_id, email, auth_method } = value;
  if (
    typeof user_id !== "string" ||
    !user_id.trim() ||
    user_id.trim().length > MAX_OWNER_LENGTH ||
    auth_method !== SESSION_AUTH_METHOD ||
    !(email === null || typeof email === "string")
  )
    return null;
  const owner = user_id.trim().toLowerCase();
  if (["shared", "service", "local"].includes(owner)) return null;
  if (owner === "__operator__") {
    if (typeof email !== "string") return null;
    const address = email.trim();
    const at = address.indexOf("@");
    if (
      !address ||
      address.length > MAX_EMAIL_LENGTH ||
      at <= 0 ||
      at === address.length - 1 ||
      address.indexOf("@", at + 1) !== -1
    )
      return null;
  }
  return Object.freeze({ user_id, email, auth_method });
}
export function createModelExecutionScope() {
  let current: ModelExecutionScope = Object.freeze({
    kind: "suspended",
    epoch: 0,
    reason: "checking_identity",
  });
  return {
    readCurrent: () => current,
    isCurrent: (scope: ReadyModelScope) => current === scope,
    suspend: (reason: SuspensionReason): ModelExecutionScope =>
      (current = Object.freeze({
        kind: "suspended",
        epoch: current.epoch + 1,
        reason,
      })),
    verify: (value: unknown): ModelExecutionScope => {
      const identity = parseModelIdentity(value);
      current = identity
        ? Object.freeze({ kind: "ready", epoch: current.epoch + 1, identity })
        : Object.freeze({
            kind: "suspended",
            epoch: current.epoch + 1,
            reason: "invalid_model_identity",
          });
      return current;
    },
  };
}
