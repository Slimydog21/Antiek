import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { LemonButton } from "../lemon";

export interface ResearchArtifactReceiptProps {
  investigationId?: string;
  artifactPath?: string | null;
  twinNotesPath?: string | null;
  documentId?: string;
  pageIndex?: number;
}

function cleanPath(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function basename(path: string): string {
  const parts = path.split("/");
  return parts[parts.length - 1] || path;
}

export default function ResearchArtifactReceipt({
  investigationId,
  artifactPath,
  twinNotesPath,
  documentId,
  pageIndex,
}: ResearchArtifactReceiptProps) {
  const navigate = useNavigate();
  const [copied, setCopied] = useState<string | null>(null);
  const paths = useMemo(
    () =>
      [
        { key: "artifact", label: "Artifact HTML", value: cleanPath(artifactPath) },
        { key: "notes", label: "Twin notes", value: cleanPath(twinNotesPath) },
      ].filter((p): p is { key: string; label: string; value: string } => Boolean(p.value)),
    [artifactPath, twinNotesPath],
  );

  const copy = async (key: string, path: string) => {
    await navigator.clipboard?.writeText(path);
    setCopied(key);
  };

  return (
    <div className="flex h-full flex-col bg-transparent">
      <div className="space-y-4 overflow-y-auto px-5 py-4">
        <header>
          <h2 className="font-serif text-lg text-ink dark:text-bright">
            Research artifact
          </h2>
          <p className="mt-0.5 text-[12px] leading-relaxed text-shadow-1 dark:text-moonlight">
            {documentId ? `From ${documentId}` : "From reading"}
            {typeof pageIndex === "number" ? `, page ${pageIndex + 1}` : ""}
          </p>
        </header>

        {paths.length > 0 ? (
          <ul className="space-y-2">
            {paths.map((path) => (
              <li
                key={path.key}
                className="rounded-hog border border-ink/10 bg-ice-0/50 p-3 dark:border-bright/10 dark:bg-charcoal-2/50"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="font-mono text-[11px] uppercase text-shadow-2 dark:text-moonlight">
                      {path.label}
                    </p>
                    <p className="truncate font-mono text-[12px] text-ink dark:text-bright" title={path.value}>
                      {basename(path.value)}
                    </p>
                  </div>
                  <LemonButton
                    type="button"
                    size="sm"
                    variant="tertiary"
                    onClick={() => void copy(path.key, path.value)}
                  >
                    {copied === path.key ? "Copied" : "Copy"}
                  </LemonButton>
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm italic text-shadow-1 dark:text-moonlight">
            No artifact path was returned.
          </p>
        )}

        {investigationId && (
          <LemonButton
            type="button"
            variant="secondary"
            size="sm"
            onClick={() => navigate(`/inv/${encodeURIComponent(investigationId)}`)}
          >
            Open research
          </LemonButton>
        )}
      </div>
    </div>
  );
}
