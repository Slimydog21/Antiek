import { useCallback, useEffect, useId, useRef, useState } from "react";
import { LemonModal } from "../lemon/LemonModal";
import {
  DEFAULT_READING_TYPOGRAPHY, READING_FONTS, readingFont, readingTypographyStyle,
  resetReadingTypography, setReadingTypography, useReadingTypography,
} from "../../lib/readingTypography";
import "../../design/readingTypography.css";

const SELECT_CLASS = "w-full min-w-0 rounded border border-rule bg-card px-3 py-2 text-sm text-1";

function FontAvailability() {
  const preferences = useReadingTypography();
  const [failedFont, setFailedFont] = useState<string | null>(null);
  useEffect(() => {
    if (preferences.font === "system" || !document.fonts) return;
    let active = true;
    const family = readingFont(preferences.font).family;
    document.fonts.load(`400 20px "${family}"`).then(
      (fonts) => { if (active) setFailedFont(fonts.length ? null : preferences.font); },
      () => { if (active) setFailedFont(preferences.font); },
    );
    return () => { active = false; };
  }, [preferences.font]);
  if (failedFont !== preferences.font) return null;
  return (
    <p role="status" className="text-xs text-2">
      This font could not load. Your reading continues in a system font. Reload this page or choose another font.
    </p>
  );
}

export function ReadingTypographyControls() {
  const preferences = useReadingTypography();
  const id = useId();
  const selected = readingFont(preferences.font);
  return (
    <div className="reading-typography-controls grid gap-4">
      <div className="grid gap-1.5">
        <label htmlFor={`${id}-font`} className="text-sm font-medium text-1">Reading font</label>
        <select id={`${id}-font`} value={preferences.font} className={SELECT_CLASS}
          aria-describedby={`${id}-description`} onChange={(event) => {
            const font = READING_FONTS.find((item) => item.id === event.target.value);
            if (font) setReadingTypography({ font: font.id });
          }}>
          {READING_FONTS.map((font) => <option key={font.id} value={font.id}>{font.name}</option>)}
        </select>
        <p id={`${id}-description`} className="text-xs text-2">{selected.description}</p>
        <FontAvailability />
      </div>
      <div className="reading-type-adjustments grid grid-cols-2 gap-x-4 gap-y-3">
        <div className="grid gap-1.5">
          <label htmlFor={`${id}-size`} className="text-sm font-medium text-1">Text size <span className="font-normal">{preferences.size} px</span></label>
          <input id={`${id}-size`} type="range" min="14" max="32" step="1" value={preferences.size}
            aria-valuetext={`${preferences.size} pixels`} className="w-full min-h-11"
            onChange={(event) => setReadingTypography({ size: event.target.valueAsNumber })} />
        </div>
        <div className="grid gap-1.5">
          <label htmlFor={`${id}-line`} className="text-sm font-medium text-1">Line spacing <span className="font-normal">{preferences.lineHeight.toFixed(2)}</span></label>
          <input id={`${id}-line`} type="range" min="1.4" max="2.2" step="0.05" value={preferences.lineHeight}
            aria-valuetext={`${preferences.lineHeight.toFixed(2)} times text size`} className="w-full min-h-11"
            onChange={(event) => setReadingTypography({ lineHeight: event.target.valueAsNumber })} />
        </div>
        <div className="grid gap-1.5">
          <label htmlFor={`${id}-measure`} className="text-sm font-medium text-1">Line width</label>
          <select id={`${id}-measure`} className={SELECT_CLASS} value={preferences.measure}
            onChange={(event) => setReadingTypography({ measure: Number(event.target.value) })}>
            <option value="52">Narrow</option><option value="66">Balanced</option><option value="78">Wide</option>
          </select>
        </div>
        <div className="grid gap-1.5">
          <label htmlFor={`${id}-letters`} className="text-sm font-medium text-1">Letter spacing</label>
          <select id={`${id}-letters`} className={SELECT_CLASS} value={preferences.letterSpacing}
            onChange={(event) => setReadingTypography({ letterSpacing: Number(event.target.value) })}>
            <option value="0">Natural</option><option value="0.03">Relaxed</option><option value="0.06">Open</option>
          </select>
        </div>
      </div>
      <div className="reading-font-preview" aria-label="Reading font preview">
        <div className="reading-prose" style={readingTypographyStyle(preferences)}>
          <p>The best place to think is one where you can forget the page and follow the thought. A quiet sentence leaves room for an unexpected idea.</p>
          <p className="mt-3"><em>Read at your own pace.</em> <strong>Keep what matters.</strong></p>
          <p className="mt-3" aria-label="Letter and number comparison">Il1 · O0 · rn m · é ö ñ · 0123456789</p>
        </div>
      </div>
      <p className="text-xs text-2">Different readers find different fonts easier. Try a few paragraphs and keep what feels comfortable. Your choices apply across Antiek in this browser.</p>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <button type="button" className="rounded border border-rule px-3 py-2 text-sm text-1 hover:bg-inset" onClick={resetReadingTypography}>Reset reading type</button>
        <span className="text-xs text-2">Default: {readingFont(DEFAULT_READING_TYPOGRAPHY.font).name}</span>
      </div>
    </div>
  );
}

export default function ReadingTypography() {
  const trigger = useRef<HTMLButtonElement>(null);
  const [open, setOpen] = useState(false);
  const close = useCallback(() => {
    setOpen(false);
    trigger.current?.focus();
  }, []);
  return (
    <>
      <button type="button" ref={trigger} aria-label="Reading type" title="Reading type"
        aria-haspopup="dialog" aria-expanded={open} onClick={() => setOpen(true)}
        className="shrink-0 min-h-11 min-w-11 rounded border border-rule px-2 py-1 font-serif text-base text-1 hover:bg-inset">
        Type
      </button>
      <LemonModal open={open} onClose={close} title="Reading type" size="md">
        <div className="reading-typography-dialog"><ReadingTypographyControls /></div>
      </LemonModal>
    </>
  );
}
