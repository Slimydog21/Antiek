import type { Meta, StoryObj } from "@storybook/react";
import { useEffect, useState } from "react";

import { accent, sun, surface } from "../../design/tokens";
import ArtifactFeedbackReview from "./ArtifactFeedbackReview";

const REVIEW_HTML = `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><style>
body{margin:0;padding:32px;background:${surface.day[2]};color:${surface.day[9]};font:17px/1.65 Charter,Georgia,serif}
main{max-width:680px;margin:auto}h1{font-size:32px;line-height:1.15}.kicker{font:700 11px/1.2 ui-monospace;letter-spacing:.12em;text-transform:uppercase;color:${accent.aurora.day}}
.finding{margin:24px 0;padding:18px 20px;border:1px solid ${surface.day[4]};border-left:4px solid ${accent.aurora.day};background:${surface.day[0]}}.source{font:12px/1.4 ui-monospace;color:${surface.day[7]}}
::selection{background:${sun.highlight.day};color:${surface.day[9]}}
</style></head><body><main><p class="kicker">Research artifact · immutable version 2</p><h1>What makes a research feedback loop trustworthy?</h1><div class="finding"><p data-antiek-node-id="insight-1" data-antiek-source-document-id="doc-1">A useful feedback loop keeps the human comment attached to the exact evidence-bearing version the reader saw.</p><p class="source">Primary paper · node insight-1</p></div><div class="finding"><p data-antiek-node-id="insight-2" data-antiek-source-document-id="doc-2">Agent replies should remain visible beside the passage instead of disappearing into terminal history.</p><p class="source">System design memo · node insight-2</p></div></main></body></html>`;

function ReviewHarness() {
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    const next = URL.createObjectURL(new Blob([REVIEW_HTML], { type: "text/html" }));
    setUrl(next);
    return () => URL.revokeObjectURL(next);
  }, []);
  if (!url) return <p>Preparing artifact…</p>;
  return (
    <ArtifactFeedbackReview
      investigationId="inv-story"
      previewUrl={url}
      receipt={{
        artifactId: "artifact-story",
        version: "2",
        hash: "a".repeat(64),
        sourceHash: "b".repeat(64),
      }}
      title="Trustworthy feedback artifact"
    />
  );
}

const meta = {
  title: "Research/ArtifactFeedbackReview",
  component: ReviewHarness,
  parameters: { layout: "padded" },
} satisfies Meta<typeof ReviewHarness>;

export default meta;
type Story = StoryObj<typeof meta>;

export const ReadyToSelect: Story = {};
