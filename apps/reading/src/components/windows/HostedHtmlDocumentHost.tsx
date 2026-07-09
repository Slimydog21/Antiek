/**
 * HostedHtmlDocumentHost — window-native page for marketplace / account
 * hosted books (residual bt). HTML-first only; PDF never required as view.
 *
 * Residual (bw): mounts TwinNotesPanel + ResearchContextPanel so reading
 * and research share the recursive note-taker / context flywheel on the
 * same document_id used as engagement asset_id after host seed (bv).
 *
 * Props arrive via WindowsLayer: `<Renderer {...win.payload} />`.
 */

import { ResearchContextPanel } from "../engagement/ResearchContextPanel";
import { TwinNotesPanel } from "../engagement/TwinNotesPanel";
import { useInWindow } from "./windowHostContext";

export type HostedHtmlDocumentHostProps = {
  document_id?: string;
  title?: string;
  html?: string;
  view_format?: string;
  license_class?: string;
  owner_id?: string;
  source?: string;
  __windowId?: string;
};

export default function HostedHtmlDocumentHost(
  props: HostedHtmlDocumentHostProps,
) {
  useInWindow();

  const docId = props.document_id?.trim() || "(missing document_id)";
  const title = props.title?.trim() || "Hosted document";
  const viewFormat = (props.view_format?.trim() || "html").toLowerCase();
  const isHtml = viewFormat === "html";
  const html = props.html?.trim() || "";
  const assetId = props.document_id?.trim() || "";

  return (
    <div
      className="flex h-full flex-col gap-3 bg-transparent p-6"
      data-testid="hosted-html-document-host"
      data-view-format={viewFormat}
      data-document-id={props.document_id ?? ""}
    >
      <header className="space-y-1 border-b border-black/10 pb-3 dark:border-white/10">
        <h1 className="font-serif text-lg text-ink dark:text-parchment">
          {title}
        </h1>
        <p className="text-xs font-mono text-shadow-1 dark:text-moonlight">
          {docId}
          {props.license_class ? ` · ${props.license_class}` : ""}
          {" · "}
          content stance: {isHtml ? "HTML" : viewFormat} · not PDF
        </p>
      </header>

      {!isHtml ? (
        <p
          className="text-sm font-mono text-emperor"
          data-testid="hosted-html-reject-pdf"
        >
          view_format must be html — PDF is not a valid reading surface.
        </p>
      ) : html ? (
        <div
          className="prose min-h-0 flex-1 overflow-auto text-sm text-ink dark:text-parchment"
          data-testid="hosted-html-body"
          dangerouslySetInnerHTML={{ __html: html }}
        />
      ) : (
        <p
          className="text-sm font-mono text-ink-mute"
          data-testid="hosted-html-empty"
        >
          No HTML body yet — host the book into your account first.
        </p>
      )}

      {assetId ? (
        <section
          className="mt-2 border-t border-black/10 pt-4 dark:border-white/10"
          data-testid="hosted-html-twins-mount"
          data-view-format="html"
        >
          <TwinNotesPanel assetId={assetId} spawnId={null} autoLoad />
        </section>
      ) : null}

      {assetId ? (
        <section
          className="mt-2 border-t border-black/10 pt-4 dark:border-white/10"
          data-testid="hosted-html-context-mount"
          data-view-format="html"
        >
          <ResearchContextPanel assetId={assetId} spawnId={null} />
        </section>
      ) : null}
    </div>
  );
}
