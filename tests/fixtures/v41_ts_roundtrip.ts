// TypeScript round-trip harness for the D2 v41 generated payloads.
// Compiled by tests/test_event_schema_roundtrip.py via the platform's tsc
// (--noEmit --strict). Constructs one payload per representative v41
// discriminator and narrows through the TypedPayload union. Must compile
// with zero errors; the exhaustive switch doubles as a narrowing proof.
import {
  ArtifactHighlightCreatedPayload,
  FeedbackDispatchCompletedPayload,
  FeedbackDispatchRefusedPayload,
  OwnerLaunchRoleCompletedPayload,
  DispatchRefusalCode,
  HighlightColor,
  LoopOneChildRole,
  TypedPayload,
  EVENT_SCHEMA_VERSION,
} from "../../apps/reading/src/generated/types";

const HEX = "a".repeat(64);

const highlight: ArtifactHighlightCreatedPayload = {
  action_type: "artifact.highlight.created",
  thread_id: "t-1",
  item_id: "i-1",
  artifact_id: "art-1",
  artifact_version: 1,
  artifact_content_sha256: HEX,
  artifact_source_sha256: HEX,
  anchor_node_id: "node-1",
  highlight_color: "disputed" as HighlightColor,
  provenance_digest_sha256: HEX,
};

const refused: FeedbackDispatchRefusedPayload = {
  action_type: "feedback.dispatch.refused",
  dispatch_id: "d-1",
  thread_id: "t-1",
  owner_user_id: "owner-a",
  action: "edit_in_place",
  artifact_id: "art-1",
  artifact_version: 1,
  artifact_content_sha256: HEX,
  artifact_source_sha256: HEX,
  operation_id: "op-1",
  refusal_code: "no_budget" as DispatchRefusalCode,
  remaining_budget_cents: 0,
};

const completed: FeedbackDispatchCompletedPayload = {
  action_type: "feedback.dispatch.completed",
  dispatch_id: "d-1",
  thread_id: "t-1",
  owner_user_id: "owner-a",
  action: "edit_in_place",
  artifact_id: "art-1",
  artifact_version: 1,
  artifact_content_sha256: HEX,
  artifact_source_sha256: HEX,
  outcome: "succeeded",
  attempt_no: 1,
  result_sha256: HEX,
  actual_cents: 10,
  resolution_event_id: "rev-1",
};

const role: OwnerLaunchRoleCompletedPayload = {
  action_type: "owner.launch.role.completed",
  owner_user_id: "owner-a",
  launch_claim_id: "lc-1",
  parent_dispatch_id: "d-1",
  feedback_thread_id: "t-1",
  child_investigation_id: "ci-1",
  operation_id: "op-1",
  role: "synthesizer" as LoopOneChildRole,
  run_id: "run-1",
  authority_digest_sha256: HEX,
  provider_id: "p-1",
  model_id: "m-1",
  source_handle: "sh-1",
  attempt_no: 1,
  outcome: "succeeded",
  result_sha256: HEX,
  provider_receipt_sha256: HEX,
  actual_cents: 25,
};

const payloads: TypedPayload[] = [highlight, refused, completed, role];
for (const p of payloads) {
  switch (p.action_type) {
    case "artifact.highlight.created":
      if (p.entry_kind !== "highlight") throw new Error("entry_kind");
      break;
    case "feedback.dispatch.refused":
      if (p.refusal_code !== "no_budget") throw new Error("refusal_code");
      break;
    case "feedback.dispatch.completed":
      if (p.attempt_no === 0 && p.outcome !== "cancelled") throw new Error("attempt_no");
      break;
    case "owner.launch.role.completed":
      if (!p.provider_receipt_sha256) throw new Error("receipt");
      break;
    default:
      throw new Error("unexpected discriminator");
  }
}

console.log(EVENT_SCHEMA_VERSION, payloads.length);
