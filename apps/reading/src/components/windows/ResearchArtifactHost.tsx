import { API_BASE } from "../../lib/api";
import { useAuth } from "../../lib/auth";

export interface ResearchArtifactHostProps extends Record<string, unknown> {
  investigationId?: string;
}

/** Private HTML host. Every remount and navigation re-authorizes server-side. */
export default function ResearchArtifactHost({ investigationId }: ResearchArtifactHostProps) {
  const { sessionGeneration } = useAuth();
  if (!investigationId) {
    return <p className="p-4 text-sm text-emperor">Research artifact identity is unavailable.</p>;
  }
  const src = `${API_BASE}/research/${encodeURIComponent(investigationId)}/artifact/view`;
  return (
    <iframe
      key={`${sessionGeneration}:${investigationId}`}
      src={src}
      title="Private research artifact"
      className="h-full min-h-[28rem] w-full border-0 bg-white"
      sandbox="allow-scripts"
      referrerPolicy="no-referrer"
    />
  );
}
