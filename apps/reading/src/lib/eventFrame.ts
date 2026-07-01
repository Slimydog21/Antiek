import {
  TYPED_PAYLOAD_ACTION_TYPES,
  type ActionType,
  type Event,
} from "../generated/types";

interface PingFrame {
  type: "ping";
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function isPingFrame(frame: unknown): frame is PingFrame {
  return isRecord(frame) && frame.type === "ping";
}

export function isEventFrame(frame: unknown): frame is Event {
  if (!isRecord(frame) || !isRecord(frame.payload)) return false;
  if (
    typeof frame.event_id !== "string" ||
    typeof frame.investigation_id !== "string" ||
    typeof frame.action_type !== "string" ||
    typeof frame.param_version !== "string" ||
    typeof frame.emitted_at !== "string"
  ) {
    return false;
  }

  const actionType = frame.action_type as ActionType;
  return (
    TYPED_PAYLOAD_ACTION_TYPES.has(actionType) &&
    frame.payload.action_type === actionType
  );
}
