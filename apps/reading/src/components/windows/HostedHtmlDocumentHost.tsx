import { useInWindow } from "./windowHostContext";

export type HostedHtmlDocumentHostProps = {
  document_id?: string;
  title?: string;
  html?: string;
  view_format?: string;
};

export function SandboxedHtmlFrame({ html, title }: { html: string; title: string }) {
  return (
    <iframe
      className="min-h-0 w-full flex-1 border-0 bg-white"
      data-testid="hosted-html-body"
      sandbox=""
      srcDoc={html}
      title={title}
    />
  );
}

export default function HostedHtmlDocumentHost(props: HostedHtmlDocumentHostProps) {
  useInWindow();
  const viewFormat = (props.view_format?.trim() || "html").toLowerCase();
  return (
    <div className="flex h-full flex-col gap-3 bg-transparent p-6"
      data-testid="hosted-html-document-host" data-view-format={viewFormat}>
      <header className="border-b border-black/10 pb-3 dark:border-white/10">
        <h1 className="font-serif text-lg text-ink dark:text-parchment">
          {props.title?.trim() || "Merged research"}
        </h1>
        <p className="text-xs font-mono text-shadow-1 dark:text-moonlight">
          {props.document_id?.trim() || "(missing document_id)"} · HTML
        </p>
      </header>
      {viewFormat !== "html" ? (
        <p role="alert" className="text-sm font-mono text-emperor">
          view_format must be html.
        </p>
      ) : props.html?.trim() ? (
        <SandboxedHtmlFrame
          html={props.html}
          title={props.title?.trim() || "Merged research"}
        />
      ) : (
        <p className="text-sm font-mono text-ink-mute">No HTML body available.</p>
      )}
    </div>
  );
}
