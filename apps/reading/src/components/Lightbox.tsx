/**
 * Lightbox panel — renders an image full-bleed inside a floating panel.
 *
 * Registered as `PanelKind = "Lightbox"` so notebook ImageBlocks can
 * open their src in a dedicated panel via workspace.open. Props are
 * intentionally tiny (src + alt + caption); the panel chrome
 * (handle, drag, close) is provided by PanelLayoutPanel.
 *
 * No fancy zoom / pan — those land in a future iteration. This is
 * just the spec-compliant "open this image in a dedicated panel"
 * surface.
 */
type Props = {
  src?: string | null;
  alt?: string | null;
  caption?: string | null;
};

export default function Lightbox({ src, alt, caption }: Props) {
  if (!src) {
    return (
      <div className="h-full flex items-center justify-center bg-ice-2 dark:bg-space-2 text-ink-mute dark:text-moonlight font-mono text-[12px] p-6 text-center">
        Lightbox opened without a src.
      </div>
    );
  }
  return (
    <figure className="h-full flex flex-col bg-ice-0 dark:bg-charcoal-2 overflow-hidden">
      <div className="flex-1 min-h-0 flex items-center justify-center overflow-auto p-3">
        <img
          src={src}
          alt={alt ?? ""}
          className="max-w-full max-h-full object-contain"
        />
      </div>
      {caption && (
        <figcaption className="font-serif italic text-[13.5px] text-ink-soft dark:text-starlight px-4 py-2 border-t-edge border-sun shrink-0">
          {caption}
        </figcaption>
      )}
    </figure>
  );
}
