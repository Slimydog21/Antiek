import {
  useEffect,
  useId,
  useRef,
  useState,
  type FormEvent,
  type CSSProperties,
  type KeyboardEvent,
  type WheelEvent,
} from "react";

import {
  artifactVersionUrl,
  listStyles,
  renderArtifact,
  saveStyle,
  type ProjectionStyle,
  type RenderedArtifact,
} from "../../api/styles";
import { apiFetch } from "../../lib/api";
import LemonButton from "../../components/lemon/LemonButton";
import "./StyleWheel.css";

export interface StyleWheelProps {
  artifactId: string;
  initialStyle?: string | null;
}

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : "The style service is unavailable.";
}

export default function StyleWheel({ artifactId, initialStyle }: StyleWheelProps) {
  const [styles, setStyles] = useState<ProjectionStyle[]>([]);
  const [selected, setSelected] = useState("");
  const [status, setStatus] = useState<"loading" | "ready" | "unavailable">("loading");
  const [error, setError] = useState<string | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [applying, setApplying] = useState(false);
  const [receipt, setReceipt] = useState<RenderedArtifact | null>(null);
  const [showFork, setShowFork] = useState(false);
  const [savingFork, setSavingFork] = useState(false);
  const [railActive, setRailActive] = useState(false);
  const [draft, setDraft] = useState({ name: "", label: "", description: "", theme_css: "", source_fidelity: false });
  const listRef = useRef<HTMLDivElement>(null);
  const previewRun = useRef(0);
  const applyRun = useRef(0);
  const applyController = useRef<AbortController | null>(null);
  const previewUrlRef = useRef<string | null>(null);
  const headingId = useId();

  useEffect(() => {
    const controller = new AbortController();
    setStatus("loading");
    void (async () => {
      try {
        const loaded = await listStyles(controller.signal);
        if (controller.signal.aborted) return;
        setStyles(loaded);
        let restored = loaded[0]?.name ?? "";
        if (restored) {
          try {
            const requested = loaded.some((style) => style.name === initialStyle)
              ? initialStyle ?? undefined
              : undefined;
            const current = await renderArtifact(artifactId, requested, false, controller.signal);
            if (loaded.some((style) => style.name === current.style)) {
              restored = current.style;
              const next = URL.createObjectURL(current.html);
              previewUrlRef.current = next;
              setPreviewUrl(next);
            }
          } catch (cause) {
            if (controller.signal.aborted) return;
            setError(messageOf(cause));
          }
        }
        setSelected(restored);
        setStatus("ready");
        if (!loaded.length) setError("No compatible styles are available for this artifact.");
      } catch (cause) {
        if (controller.signal.aborted) return;
        setStatus("unavailable");
        setError(messageOf(cause));
      }
    })();
    return () => controller.abort();
  }, [artifactId, initialStyle]);

  useEffect(() => {
    applyRun.current += 1;
    applyController.current?.abort();
    applyController.current = null;
    setApplying(false);
    setReceipt(null);
  }, [artifactId, selected]);

  useEffect(() => () => {
    previewRun.current += 1;
    applyRun.current += 1;
    applyController.current?.abort();
    if (previewUrlRef.current) URL.revokeObjectURL(previewUrlRef.current);
  }, []);

  useEffect(() => {
    if (!selected || status !== "ready") return;
    const controller = new AbortController();
    const run = ++previewRun.current;
    setPreviewing(true);
    setError(null);
    renderArtifact(artifactId, selected, false, controller.signal)
      .then((rendered) => {
        if (run !== previewRun.current) return;
        const next = URL.createObjectURL(rendered.html);
        if (previewUrlRef.current) URL.revokeObjectURL(previewUrlRef.current);
        previewUrlRef.current = next;
        setPreviewUrl(next);
      })
      .catch((cause) => {
        if (!controller.signal.aborted && run === previewRun.current) {
          setPreviewUrl(null);
          setError(messageOf(cause));
        }
      })
      .finally(() => {
        if (run === previewRun.current) setPreviewing(false);
      });
    return () => controller.abort();
  }, [artifactId, selected, status]);

  const chooseAt = (index: number) => {
    const style = styles[(index + styles.length) % styles.length];
    if (!style) return;
    setSelected(style.name);
    requestAnimationFrame(() => document.getElementById(`style-${style.name}`)?.focus());
  };

  const onKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    if (!["ArrowRight", "ArrowLeft", "ArrowUp", "ArrowDown", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    if (event.key === "Home") chooseAt(0);
    else if (event.key === "End") chooseAt(styles.length - 1);
    else chooseAt(index + (["ArrowRight", "ArrowDown"].includes(event.key) ? 1 : -1));
  };

  const onWheel = (event: WheelEvent<HTMLDivElement>) => {
    if (!railActive || Math.abs(event.deltaY) <= Math.abs(event.deltaX)) return;
    event.preventDefault();
    event.currentTarget.scrollLeft += event.deltaY;
  };

  const onSaveFork = async (event: FormEvent) => {
    event.preventDefault();
    setSavingFork(true);
    setError(null);
    try {
      const saved = await saveStyle(draft);
      setStyles((current) => {
        const at = current.findIndex((style) => style.name === saved.name);
        if (at < 0) return [...current, saved];
        return current.map((style, index) => index === at ? saved : style);
      });
      setSelected(saved.name);
      setShowFork(false);
    } catch (cause) {
      setError(messageOf(cause));
    } finally {
      setSavingFork(false);
    }
  };

  const apply = async () => {
    applyController.current?.abort();
    const controller = new AbortController();
    applyController.current = controller;
    const run = ++applyRun.current;
    setApplying(true);
    setError(null);
    try {
      const next = await renderArtifact(artifactId, selected, true, controller.signal);
      if (run === applyRun.current && !controller.signal.aborted) setReceipt(next);
    } catch (cause) {
      if (run === applyRun.current && !controller.signal.aborted) setError(messageOf(cause));
    } finally {
      if (run === applyRun.current) setApplying(false);
    }
  };

  const openVersion = (version?: string) => {
    window.open(artifactVersionUrl(artifactId, version), "_blank", "noopener,noreferrer");
  };

  const downloadVersion = async (version?: string) => {
    try {
      const response = await apiFetch(artifactVersionUrl(artifactId, version));
      if (!response.ok) throw new Error(`Download unavailable (HTTP ${response.status}).`);
      const url = URL.createObjectURL(await response.blob());
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `research-${artifactId}-${version ?? "latest"}.html`;
      anchor.click();
      setTimeout(() => URL.revokeObjectURL(url), 0);
    } catch (cause) {
      setError(messageOf(cause));
    }
  };

  if (status === "loading") return <p className="style-wheel__state" role="status">Loading style wheel…</p>;
  if (status === "unavailable") return <p className="style-wheel__state style-wheel__state--error" role="alert">Styles unavailable · {error}</p>;

  const active = styles.find((style) => style.name === selected);
  return (
    <section className="style-wheel" aria-labelledby={headingId}>
      <div className="style-wheel__header">
        <div>
          <p className="style-wheel__eyebrow">Research artifact</p>
          <h3 id={headingId}>Choose its reading style</h3>
        </div>
        <button type="button" className="style-wheel__fork-toggle" onClick={() => setShowFork((value) => !value)} aria-expanded={showFork}>
          {showFork ? "Close style editor" : "Fork a style"}
        </button>
      </div>

      <div
        className="style-wheel__rail"
        ref={listRef}
        role="listbox"
        aria-label="Artifact styles"
        aria-orientation="horizontal"
        onWheel={onWheel}
        onMouseEnter={() => setRailActive(true)}
        onMouseLeave={() => setRailActive(false)}
        onFocusCapture={() => setRailActive(true)}
        onBlurCapture={(event) => {
          if (!event.currentTarget.contains(event.relatedTarget)) setRailActive(false);
        }}
      >
        {styles.map((style, index) => (
          <button
            id={`style-${style.name}`}
            key={style.name}
            type="button"
            role="option"
            aria-selected={style.name === selected}
            tabIndex={style.name === selected ? 0 : -1}
            className="style-wheel__option"
            onClick={() => setSelected(style.name)}
            onKeyDown={(event) => onKeyDown(event, index)}
          >
            <span className="style-wheel__swatch" style={{ "--style-theme": style.source_fidelity ? "var(--ocean)" : "var(--sun-deep)" } as CSSProperties} aria-hidden="true" />
            <strong>{style.label}</strong>
            <span>{style.builtin ? "Built in" : "Your fork"}{style.source_fidelity ? " · source-first" : ""}</span>
          </button>
        ))}
      </div>

      {active ? <p className="style-wheel__description"><strong>{active.label}.</strong> {active.description || "No description provided."}</p> : null}

      {showFork ? (
        <form className="style-wheel__form" onSubmit={onSaveFork}>
          <label>Slug <input required maxLength={64} pattern="[a-z0-9][a-z0-9_-]*" value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} placeholder="field-notes" /></label>
          <label>Label <input required maxLength={128} value={draft.label} onChange={(e) => setDraft({ ...draft, label: e.target.value })} placeholder="Field notes" /></label>
          <label className="style-wheel__wide">Description <input maxLength={2048} value={draft.description} onChange={(e) => setDraft({ ...draft, description: e.target.value })} /></label>
          <label className="style-wheel__wide">Theme CSS <textarea maxLength={100000} rows={6} value={draft.theme_css} onChange={(e) => setDraft({ ...draft, theme_css: e.target.value })} placeholder=":root { --antiek-accent: var(--ocean); }" /></label>
          <label className="style-wheel__check"><input type="checkbox" checked={draft.source_fidelity} onChange={(e) => setDraft({ ...draft, source_fidelity: e.target.checked })} /> Preserve source-first treatment</label>
          <div><LemonButton size="sm" disabled={savingFork} type="submit">{savingFork ? "Saving…" : "Save fork"}</LemonButton></div>
        </form>
      ) : null}

      {error ? <p className="style-wheel__error" role="alert">{error}</p> : null}
      <div className="style-wheel__preview-shell" aria-busy={previewing}>
        {previewUrl ? <iframe title={`${active?.label ?? "Style"} artifact preview`} sandbox="" src={previewUrl} /> : <p>{previewing ? "Building a script-free preview…" : "Preview unavailable for this artifact."}</p>}
      </div>
      <div className="style-wheel__actions">
        <LemonButton disabled={!selected || applying || previewing} onClick={() => void apply()}>{applying ? "Applying…" : `Apply ${active?.label ?? "style"}`}</LemonButton>
        <span>Preview is temporary. Apply creates a durable version.</span>
      </div>

      {receipt ? (
        <aside className="style-wheel__receipt" aria-live="polite">
          <strong>Version {receipt.version} saved</strong>
          <dl><div><dt>Style</dt><dd>{receipt.style}</dd></div><div><dt>SHA-256</dt><dd title={receipt.hash}>{receipt.hash}</dd></div></dl>
          <div className="style-wheel__receipt-actions">
            <button type="button" onClick={() => openVersion(receipt.version)}>Open version {receipt.version}</button>
            <button type="button" onClick={() => void downloadVersion(receipt.version)}>Download version {receipt.version}</button>
            <button type="button" onClick={() => openVersion()}>Open latest</button>
            <button type="button" onClick={() => void downloadVersion()}>Download latest</button>
          </div>
        </aside>
      ) : null}
    </section>
  );
}
