/**
 * ResearchBlock — one pasted deep-research output as a Lego block.
 * Three sizes (mini / standard / expanded), keyboard accessible.
 * Composed from LemonCard + LemonTag.
 */

import type { KeyboardEvent, DragEvent } from "react";
import { LemonCard, LemonTag } from "../../components/lemon";
import type { ResearchBlockSummary } from "./types";
import { SOURCE_VISUAL } from "./types";
import { beginBlockDrag } from "./drag";

export type ResearchBlockSize = "mini" | "standard" | "expanded";

export interface ResearchBlockProps {
  block: ResearchBlockSummary;
  size?: ResearchBlockSize;
  selected?: boolean;
  onActivate?: (block: ResearchBlockSummary) => void;
  onHover?: (block: ResearchBlockSummary | null) => void;
  draggable?: boolean;
  className?: string;
}

function _formatBytes(n: number): string {
  if (n < 1024) return `${n}B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)}KB`;
  return `${(n / (1024 * 1024)).toFixed(1)}MB`;
}

function _confidenceTone(c: number): "sun" | "muted" | "danger" {
  if (c >= 0.7) return "sun";
  if (c >= 0.4) return "muted";
  return "danger";
}

export function ResearchBlock({
  block,
  size = "standard",
  selected = false,
  onActivate,
  onHover,
  draggable = true,
  className,
}: ResearchBlockProps) {
  const visual = SOURCE_VISUAL[block.source];

  const handleDragStart = (e: DragEvent<HTMLDivElement>) => {
    beginBlockDrag(e, block);
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (!onActivate) return;
    if (e.key === " " || e.key === "Enter") {
      e.preventDefault();
      onActivate(block);
    }
  };

  const rootClasses = [
    "outline-none focus-visible:ring-2 focus-visible:ring-sun-deep rounded-md",
    selected ? "ring-2 ring-sun-deep" : "",
    draggable ? "cursor-grab active:cursor-grabbing" : "",
    onActivate ? "cursor-pointer" : "",
    className ?? "",
  ].filter(Boolean).join(" ");

  if (size === "mini") {
    return (
      <div
        role="button"
        tabIndex={onActivate ? 0 : -1}
        className={rootClasses}
        draggable={draggable}
        onDragStart={draggable ? handleDragStart : undefined}
        onClick={onActivate ? () => onActivate(block) : undefined}
        onKeyDown={handleKeyDown}
        onMouseEnter={onHover ? () => onHover(block) : undefined}
        onMouseLeave={onHover ? () => onHover(null) : undefined}
        data-research-block-id={block.document_id}
      >
        <LemonCard elevation="z1" colour="card">
          <div className="flex items-center gap-2 text-xs">
            <LemonTag colour={visual.tagColour}>{visual.label}</LemonTag>
            <span className="truncate font-medium text-ink dark:text-bright">
              {block.title ?? `(${visual.label} paste)`}
            </span>
          </div>
        </LemonCard>
      </div>
    );
  }

  if (size === "standard") {
    return (
      <div
        role="button"
        tabIndex={onActivate ? 0 : -1}
        className={rootClasses}
        draggable={draggable}
        onDragStart={draggable ? handleDragStart : undefined}
        onClick={onActivate ? () => onActivate(block) : undefined}
        onKeyDown={handleKeyDown}
        onMouseEnter={onHover ? () => onHover(block) : undefined}
        onMouseLeave={onHover ? () => onHover(null) : undefined}
        data-research-block-id={block.document_id}
      >
        <LemonCard elevation="z2" colour="card">
          <div className="flex flex-col gap-2">
            <div className="flex items-center gap-2 text-xs">
              <LemonTag colour={visual.tagColour}>{visual.label}</LemonTag>
              <LemonTag colour={_confidenceTone(block.source_confidence)}>
                {Math.round(block.source_confidence * 100)}%
              </LemonTag>
              <span className="ml-auto text-shadow-2 dark:text-moonlight">
                {_formatBytes(block.paste_byte_length)}
              </span>
            </div>
            <div className="text-sm font-medium leading-tight text-ink dark:text-bright">
              {block.title ?? `(${visual.label} paste)`}
            </div>
            {(block.operator_label || block.session_id) && (
              <div className="text-xs text-shadow-2 dark:text-moonlight truncate">
                {block.operator_label ?? ""}
                {block.operator_label && block.session_id ? " · " : ""}
                {block.session_id ?? ""}
              </div>
            )}
            {(block.insight_count !== undefined ||
              block.open_question_count !== undefined) && (
              <div className="flex gap-2 text-xs">
                {block.insight_count !== undefined && (
                  <span className="text-shadow-2 dark:text-moonlight">
                    {block.insight_count} insight{block.insight_count === 1 ? "" : "s"}
                  </span>
                )}
                {block.open_question_count !== undefined && (
                  <span className="text-shadow-2 dark:text-moonlight">
                    {block.open_question_count} open Q
                  </span>
                )}
              </div>
            )}
          </div>
        </LemonCard>
      </div>
    );
  }

  return (
    <div
      role="button"
      tabIndex={onActivate ? 0 : -1}
      className={rootClasses}
      draggable={draggable}
      onDragStart={draggable ? handleDragStart : undefined}
      onClick={onActivate ? () => onActivate(block) : undefined}
      onKeyDown={handleKeyDown}
      onMouseEnter={onHover ? () => onHover(block) : undefined}
      onMouseLeave={onHover ? () => onHover(null) : undefined}
      data-research-block-id={block.document_id}
    >
      <LemonCard
        elevation="z3"
        colour="card"
        title={
          <div className="flex items-center gap-2">
            <LemonTag colour={visual.tagColour}>{visual.label}</LemonTag>
            <LemonTag colour={_confidenceTone(block.source_confidence)}>
              detected {Math.round(block.source_confidence * 100)}%
            </LemonTag>
            <span className="ml-auto text-xs text-shadow-2 dark:text-moonlight">
              {_formatBytes(block.paste_byte_length)} · {block.pasted_at}
            </span>
          </div>
        }
        footer={
          (block.insight_count !== undefined ||
           block.open_question_count !== undefined) ? (
            <div className="flex gap-3 text-xs text-shadow-2 dark:text-moonlight">
              {block.insight_count !== undefined && (
                <span>{block.insight_count} extracted insight{block.insight_count === 1 ? "" : "s"}</span>
              )}
              {block.open_question_count !== undefined && (
                <span>{block.open_question_count} open question{block.open_question_count === 1 ? "" : "s"}</span>
              )}
            </div>
          ) : undefined
        }
      >
        <div className="flex flex-col gap-2">
          <div className="text-sm font-medium leading-tight text-ink dark:text-bright">
            {block.title ?? `(${visual.label} paste)`}
          </div>
          {block.operator_label && (
            <div className="text-xs text-shadow-2 dark:text-moonlight">
              <span className="font-bold">Label:</span> {block.operator_label}
            </div>
          )}
          {block.session_id && (
            <div className="text-xs text-shadow-2 dark:text-moonlight">
              <span className="font-bold">Session:</span> {block.session_id}
            </div>
          )}
          {block.preview_text && (
            <div className="text-xs text-ink dark:text-bright max-h-48 overflow-auto whitespace-pre-wrap border-l-2 border-rule dark:border-charcoal-2 pl-2 mt-1">
              {block.preview_text}
            </div>
          )}
        </div>
      </LemonCard>
    </div>
  );
}
