import { lazy, Suspense, useEffect, useState } from "react";

import { LemonModal } from "../components/lemon/LemonModal";
import { LoadingState } from "../components/states";
import { topModal } from "./escapeOverlay";
import { useWorkspace } from "./WorkspaceStore";

const ProjectTree = lazy(() => import("../shell/ProjectTree"));

export default function ProjectTreeOverlay() {
  const [origin] = useState(() => document.activeElement);
  useEffect(() => () => {
    const modal = topModal();
    const originVisible = origin instanceof HTMLElement && origin !== document.body &&
      origin.isConnected && !origin.closest('[hidden], [aria-hidden="true"]') &&
      origin.matches("button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), a[href], [tabindex], [contenteditable='true']");
    const target = modal ?? (originVisible ? origin :
      Array.from(document.querySelectorAll<HTMLElement>('[data-pane], [data-cockpit-content]'))
        .find((el) => !el.closest('[hidden], [aria-hidden="true"]')));
    target?.focus();
  }, [origin]);

  return (
    <LemonModal
      open
      title="Project"
      size="sm"
      onClose={() => useWorkspace.getState().close("shortcuts:projecttree")}
    >
      <div className="max-h-[70vh] overflow-auto">
        <Suspense fallback={<LoadingState variant="inline" label="Opening your projects" />}>
          <ProjectTree />
        </Suspense>
      </div>
    </LemonModal>
  );
}
