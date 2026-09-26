import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { LemonButton } from "../lemon";
import { API_BASE, getDistillation } from "../../lib/api";
import type { DistilledNode } from "../../lib/api";
import FlagForDiligence from "../../shared/FlagForDiligence";

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

function artifactViewHref(investigationId: string, kind: "artifact" | "notes"): string {
  const encoded = encodeURIComponent(investigationId);
  const suffix = kind === "artifact" ? "html" : "twin-notes.html";
  return `${API_BASE}/research/${encoded}/artifact/${suffix}`;
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
          <p className="mt-0.5 text-xs leading-relaxed text-shadow-1 dark:text-moonlight">
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
                    <p className="font-mono text-xs uppercase text-shadow-2 dark:text-moonlight">
                      {path.label}
                    </p>
                    <p className="truncate font-mono text-xs text-ink dark:text-bright" title={path.value}>
                      {basename(path.value)}
                    </p>
                  </div>
                  <div className="flex shrink-0 items-center gap-1">
                    {investigationId && (
                      <a
                        href={artifactViewHref(
                          investigationId,
                          path.key === "artifact" ? "artifact" : "notes",
                        )}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex h-7 items-center rounded-hog px-2 font-mono text-xs font-semibold text-ink hover:bg-ice-3 dark:text-bright dark:hover:bg-charcoal-1"
                      >
                        Open
                      </a>
                    )}
                    <LemonButton
                      type="button"
                      size="sm"
                      variant="tertiary"
                      onClick={() => void copy(path.key, path.value)}
                    >
                      {copied === path.key ? "Copied" : "Copy"}
                    </LemonButton>
                  </div>
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

        {/* Autonomous-diligence SPR-01: the receipt's open questions carry
            the calm flag affordance (refs only — never the question's text
            in the request). */}
        {investigationId && <OpenQuestions investigationId={investigationId} />}
      </div>
    </div>
  );
}

function OpenQuestions({ investigationId }: { investigationId: string }) {
  const [questions, setQuestions] = useState<DistilledNode[] | null>(null);
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const res = await getDistillation(investigationId);
        if (!cancelled) setQuestions(res.questions);
      } catch {
        // A failed distill read is an honest empty section, never a crash —
        // the receipt itself (the window's point) is unaffected.
        if (!cancelled) setQuestions([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [investigationId]);

  if (questions === null || questions.length === 0) return null;
  return (
    <section data-receipt-questions>
      <h3 className="mb-1.5 font-mono text-xs uppercase tracking-wider text-shadow-1 dark:text-moonlight">
        Open questions
      </h3>
      <ul className="space-y-1.5">
        {questions.map((q) => (
          <li key={q.node_id} className="text-sm font-serif leading-relaxed text-ink dark:text-bright">
            ? {q.text}
            <span className="ml-2 align-middle text-xs text-shadow-1 dark:text-moonlight">
              <FlagForDiligence node={q} sourceInvestigationId={investigationId} />
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
