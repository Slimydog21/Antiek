import { useCallback, useRef, useState, type DragEvent, type ReactNode } from "react";

import { classifyText } from "./intakeKinds";

/**
 * DropZone — the zen box's drop target (FFX-KPA SPR-03 M3).
 *
 * dragenter/dragleave fire for every child the pointer crosses, so a boolean
 * flickers the overlay. A depth counter (refs/agent-pane-refs.md, Grok
 * composer) keeps it steady: +1 on enter, -1 on leave, overlay while > 0,
 * reset on drop. The zone only hands files and URLs up; deciding what is
 * accepted is intakeKinds' job, so nothing here reads or sends a file.
 */
interface Props {
  onFiles: (files: File[]) => void;
  onUrl: (url: string) => void;
  disabled?: boolean;
  className?: string;
  children: ReactNode;
}

const carriesSomething = (e: DragEvent) => {
  const types = Array.from(e.dataTransfer?.types ?? []);
  return types.includes("Files") || types.includes("text/uri-list") || types.includes("text/plain");
};

export default function DropZone({ onFiles, onUrl, disabled, className, children }: Props) {
  const depth = useRef(0);
  const [active, setActive] = useState(false);

  const onDragEnter = useCallback((e: DragEvent) => {
    if (disabled || !carriesSomething(e)) return;
    e.preventDefault();
    depth.current += 1;
    setActive(true);
  }, [disabled]);

  const onDragLeave = useCallback((e: DragEvent) => {
    if (disabled || depth.current === 0) return;
    e.preventDefault();
    depth.current -= 1;
    if (depth.current === 0) setActive(false);
  }, [disabled]);

  const onDragOver = useCallback((e: DragEvent) => {
    if (disabled || !carriesSomething(e)) return;
    e.preventDefault(); // required for the drop to fire
  }, [disabled]);

  const onDrop = useCallback((e: DragEvent) => {
    depth.current = 0;
    setActive(false);
    if (disabled) return;
    e.preventDefault();
    const files = Array.from(e.dataTransfer?.files ?? []);
    if (files.length > 0) {
      onFiles(files);
      return;
    }
    const text = e.dataTransfer?.getData("text/uri-list") || e.dataTransfer?.getData("text/plain") || "";
    const first = text.split(/\r?\n/).find((line) => line.trim() && !line.startsWith("#")) ?? "";
    if (classifyText(first)) onUrl(first.trim());
  }, [disabled, onFiles, onUrl]);

  return (
    <div
      className={`relative ${className ?? ""}`}
      data-drop-active={active || undefined}
      onDragEnter={onDragEnter}
      onDragLeave={onDragLeave}
      onDragOver={onDragOver}
      onDrop={onDrop}
    >
      {children}
      {active && (
        <div
          aria-hidden="true"
          data-testid="zen-drop-overlay"
          className="pointer-events-none absolute inset-0 flex items-center justify-center rounded-hog-lg border-2 border-dashed border-sun-deep bg-ice-0/90 dark:bg-charcoal-2/90 text-sm font-sans text-ink dark:text-bright"
        >
          Drop to attach
        </div>
      )}
    </div>
  );
}
