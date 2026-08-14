/**
 * ReleaseNotesModal — staged, seen-once release notes (herdr transfer P2).
 * Auto-opens once per version (mounted in AppShell); Settings re-opens it
 * via the "antiek:open-release-notes" window event. Dismiss marks seen.
 */
import { useEffect, useState } from "react";

import { LemonModal } from "./lemon/LemonModal";
import {
  hasSeenRelease,
  latestReleaseNote,
  markReleaseSeen,
} from "../shared/releaseNotes";

export function ReleaseNotesModal() {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const latest = latestReleaseNote();
    if (!hasSeenRelease(latest.version)) setOpen(true);
    // Settings → "What's new" re-opens it.
    const onOpen = () => setOpen(true);
    window.addEventListener("antiek:open-release-notes", onOpen);
    return () =>
      window.removeEventListener("antiek:open-release-notes", onOpen);
  }, []);

  const close = () => {
    setOpen(false);
    markReleaseSeen(latestReleaseNote().version);
  };

  const note = latestReleaseNote();

  return (
    <LemonModal open={open} onClose={close} title={`What's new — ${note.title}`}>
      <div className="p-4 space-y-2">
        <p className="font-mono text-[11px] text-shadow-1 dark:text-moonlight">
          {note.date} · {note.version}
        </p>
        <ul className="space-y-2">
          {note.items.map((item) => (
            <li
              key={item}
              className="flex items-start gap-2 text-[13.5px] leading-relaxed"
            >
              <span
                aria-hidden="true"
                className="mt-[7px] h-1.5 w-1.5 shrink-0 rounded-full bg-aurora"
              />
              <span>{item}</span>
            </li>
          ))}
        </ul>
      </div>
    </LemonModal>
  );
}
