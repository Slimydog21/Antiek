import { useEffect, useRef, useState } from "react";

import { LemonButton } from "../../components/lemon";
import {
  getDeliverable,
  listDeliverables,
  type DeliverableDetailResponse,
  type DeliverableSummary,
} from "../../lib/api";
import { handoffReadNoteToWrite } from "../Write/writeApi";

export default function ReadToWritePicker({
  noteId,
  investigationId,
  onClose,
  onComplete,
}: {
  noteId: string;
  investigationId: string;
  onClose: () => void;
  onComplete: (deliverableId: string) => void;
}) {
  const [pieces, setPieces] = useState<DeliverableSummary[] | null>(null);
  const [piece, setPiece] = useState<DeliverableDetailResponse | null>(null);
  const [busySection, setBusySection] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const dialogRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const dialog = dialogRef.current;
    dialog?.querySelector<HTMLElement>("button")?.focus();
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key !== "Tab" || !dialog) return;
      const controls = Array.from(
        dialog.querySelectorAll<HTMLElement>('button:not([disabled]), [href], [tabindex]:not([tabindex="-1"])'),
      );
      if (!controls.length) return;
      const first = controls[0];
      const last = controls[controls.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      previous?.focus();
    };
  }, [onClose]);

  useEffect(() => {
    let live = true;
    listDeliverables()
      .then((result) => live && setPieces(result.deliverables))
      .catch((cause) => live && setError(cause instanceof Error ? cause.message : String(cause)));
    return () => { live = false; };
  }, []);

  async function choosePiece(deliverableId: string) {
    setError(null);
    try { setPiece(await getDeliverable(deliverableId)); }
    catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); }
  }

  async function chooseSection(sectionId: string) {
    if (!piece) return;
    setBusySection(sectionId);
    setError(null);
    try {
      const handoff = await handoffReadNoteToWrite({
        note_id: noteId,
        target_section_id: sectionId,
        investigation_id: investigationId,
      });
      onComplete(handoff.deliverable_id);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
      setBusySection(null);
    }
  }

  return (
    <div role="dialog" aria-modal="true" aria-label="Add note to writing"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4">
      <div ref={dialogRef} className="w-full max-w-md rounded-lg border border-rule bg-ice-0 p-4 shadow-xl dark:border-charcoal-1 dark:bg-charcoal-2">
        <div className="mb-3 flex items-center justify-between gap-3">
          <h2 className="font-serif text-lg text-ink dark:text-bright">
            {piece ? `Choose a section in ${piece.title}` : "Choose a piece"}
          </h2>
          <LemonButton type="button" size="sm" variant="tertiary" onClick={onClose}>Close</LemonButton>
        </div>
        {error && <p role="alert" className="mb-3 text-sm text-danger">{error}</p>}
        {pieces === null && !error && <p className="text-sm text-shadow-1">Loading your writing…</p>}
        {pieces?.length === 0 && <p className="text-sm text-shadow-1">Start a piece in Write before adding this note.</p>}
        {!piece && pieces && pieces.length > 0 && (
          <ul className="space-y-2">
            {pieces.map((candidate) => (
              <li key={candidate.deliverable_id}>
                <LemonButton type="button" variant="secondary" onClick={() => void choosePiece(candidate.deliverable_id)}>
                  {candidate.title}
                </LemonButton>
              </li>
            ))}
          </ul>
        )}
        {piece && (
          <div>
            <LemonButton type="button" size="sm" variant="tertiary" onClick={() => setPiece(null)}>Back to pieces</LemonButton>
            {piece.sections.length === 0 ? (
              <p className="mt-3 text-sm text-shadow-1">This piece needs a section first.</p>
            ) : (
              <ul className="mt-3 space-y-2">
                {piece.sections.map((section) => (
                  <li key={section.section_id}>
                    <LemonButton type="button" variant="secondary" disabled={busySection !== null}
                      onClick={() => void chooseSection(section.section_id)}>
                      {busySection === section.section_id ? "Adding…" : section.title || "Untitled section"}
                    </LemonButton>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
