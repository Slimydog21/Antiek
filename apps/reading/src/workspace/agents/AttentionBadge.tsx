/**
 * agents/AttentionBadge.tsx — SPR-10 M6: the rollup badge (herdr R16: a
 * badge shows the max over its members) for a project or the workspace,
 * from the same store every other surface reads. Renders nothing when the
 * rollup is null (no members), never a phantom state. Mounted at base in
 * CompanionPane's strip row (workspace scope); the strip, the gear switcher
 * and the pane header are one-line mounts for their owning sprints.
 */
import { useProjectAttention, useWorkspaceAttention } from "./agentStatusStore";
import { StatusDot, type StatusDotGround } from "./StatusDot";
import type { AgentStatus } from "./agentStatus";

export type AttentionScope = { kind: "project"; id: string } | { kind: "workspace" };

export interface AttentionBadgeProps {
  scope: AttentionScope;
  ground?: StatusDotGround;
  className?: string;
}

function Badge({ status, scope, ground, className }: { status: AgentStatus | null; scope: string; ground?: StatusDotGround; className?: string }) {
  if (status === null) return null;
  return (
    <span data-attention-scope={scope} className={className}>
      <StatusDot status={status} variant="symbol" word="sr" ground={ground} />
    </span>
  );
}

function ProjectBadge({ id, ground, className }: { id: string; ground?: StatusDotGround; className?: string }) {
  const status = useProjectAttention(id);
  return <Badge status={status} scope={`project:${id}`} ground={ground} className={className} />;
}

function WorkspaceBadge({ ground, className }: { ground?: StatusDotGround; className?: string }) {
  const status = useWorkspaceAttention();
  return <Badge status={status} scope="workspace" ground={ground} className={className} />;
}

export function AttentionBadge({ scope, ground, className }: AttentionBadgeProps) {
  return scope.kind === "project"
    ? <ProjectBadge id={scope.id} ground={ground} className={className} />
    : <WorkspaceBadge ground={ground} className={className} />;
}

export default AttentionBadge;
