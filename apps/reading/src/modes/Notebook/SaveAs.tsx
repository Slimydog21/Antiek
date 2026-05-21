// SPR-11 / M5 — Save-as menu.
//
// Operator can export the current theme as:
//   - .antiek (default) — calls SPR-09's writer with
//     content_class="theme_notebook" (see services/notebooks/
//     theme_persistence.py::save_theme_as_antiek for the manifest
//     shape including source_notebook_ids).
//   - PDF (export) — round-trip via the existing PDF export pipe.
//   - Markdown (export) — plain-text dump of the ordered blocks.
//
// The .antiek path goes through the backend (Python writes the
// container so the SPR-09 binary format stays server-side); PDF
// and Markdown are also server-rendered for now. Until SPR-09
// lands, the .antiek button calls a JSON-shim endpoint with the
// same manifest shape so the round-trip test (M7) is meaningful.

import { useCallback, useState } from "react";

import type { ThemeResponse } from "../../../api/themes/by-slug";

export interface SaveAsProps {
  theme: ThemeResponse;
}

type SaveFormat = "antiek" | "pdf" | "markdown";

export default function SaveAs(props: SaveAsProps): JSX.Element {
  const [open, setOpen] = useState(false);
  const [status, setStatus] =
    useState<"idle" | "saving" | "saved" | "error">("idle");
  const [error, setError] = useState<string | null>(null);

  const save = useCallback(
    async (format: SaveFormat) => {
      setOpen(false);
      setStatus("saving");
      setError(null);
      try {
        // The actual export endpoint is a follow-up PR. For now we
        // construct the URL and let the browser dispatch a GET with
        // ?format= so the server picks the writer. A 404 here is
        // expected pre-backend-wire; we surface it cleanly.
        const url =
          `/api/themes/${encodeURIComponent(
            props.theme.theme_id,
          )}/export?format=${encodeURIComponent(format)}`;
        const res = await fetch(url, {
          method: "GET",
          credentials: "include",
        });
        if (!res.ok) {
          throw new Error(`HTTP ${res.status}`);
        }
        // Download the response body as a file. Filename derived
        // from the theme slug + format.
        const blob = await res.blob();
        const filename = `${props.theme.slug}.${
          format === "markdown" ? "md" : format
        }`;
        const objUrl = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = objUrl;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(objUrl);
        setStatus("saved");
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
        setStatus("error");
      }
    },
    [props.theme],
  );

  return (
    <div className="relative inline-flex">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className={
          "text-xs font-mono px-3 py-1.5 rounded border border-stone-300 " +
          "bg-white hover:bg-stone-50 text-stone-700"
        }
        data-testid="save-as-toggle"
        aria-expanded={open}
      >
        Save as…
      </button>
      {open && (
        <ul
          className={
            "absolute left-0 top-full mt-1 w-56 bg-white border border-stone-300 " +
            "rounded-md shadow-lg z-30 text-sm py-1"
          }
          data-testid="save-as-menu"
        >
          <li>
            <button
              type="button"
              onClick={() => void save("antiek")}
              className="w-full text-left px-3 py-1.5 hover:bg-stone-50"
              data-testid="save-as-antiek"
            >
              <span className="font-mono">.antiek</span>{" "}
              <span className="text-stone-500">(default)</span>
            </button>
          </li>
          <li>
            <button
              type="button"
              onClick={() => void save("pdf")}
              className="w-full text-left px-3 py-1.5 hover:bg-stone-50"
              data-testid="save-as-pdf"
            >
              PDF <span className="text-stone-500">(export)</span>
            </button>
          </li>
          <li>
            <button
              type="button"
              onClick={() => void save("markdown")}
              className="w-full text-left px-3 py-1.5 hover:bg-stone-50"
              data-testid="save-as-markdown"
            >
              Markdown <span className="text-stone-500">(export)</span>
            </button>
          </li>
        </ul>
      )}
      {status === "saving" && (
        <span className="ml-2 text-[11px] font-mono text-stone-500 self-center">
          saving…
        </span>
      )}
      {status === "saved" && (
        <span className="ml-2 text-[11px] font-mono text-green-700 self-center">
          saved
        </span>
      )}
      {status === "error" && (
        <span
          className="ml-2 text-[11px] font-mono text-red-700 self-center"
          title={error || undefined}
        >
          save failed
        </span>
      )}
    </div>
  );
}
