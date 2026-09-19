/**
 * releaseNotes.ts — staged, seen-once release notes (herdr transfer P2,
 * strategy 29). The latest entry auto-shows once per version; "What's new"
 * in Settings re-opens it. Content is staged data (edited here), the
 * seen-set is localStorage (versioned key).
 */
export interface ReleaseNote {
  /** Version this note describes — auto-shows once per distinct version. */
  version: string;
  title: string;
  date: string;
  items: string[];
}

export const RELEASE_NOTES: ReleaseNote[] = [
  {
    version: "2026-08-13.1",
    title: "The attention layer + workbench",
    date: "2026-08-13",
    items: [
      "Every research surface now speaks ONE state vocabulary — working, needs attention, done, stopped — with unread research shown bold.",
      "Research families roll up their attention: a blocked child reddens its whole cascade, and the rail shows how many need you.",
      "Completed research you haven't opened is UNREAD — opening it marks it seen.",
      "Toasts are clickable: a notification jumps you to the research that produced it.",
      "Press ⌘K and try state:blocked — the palette now filters by what needs you.",
      "Panels zoom to the full workspace (⤢ on any panel handle; Esc exits).",
      "The live research transcript is a document: scroll up to read, / to search, ↓ new to jump back to the tail.",
      "A quiet chime plays when research completes or needs attention — unless you're watching it (mute in Settings).",
      "The window title and favicon reflect research state — your tabs tell you when something finished.",
      "One shared research list feeds every surface: faster home, one source of truth.",
    ],
  },
];

/** The newest note (the one auto-shown). */
export function latestReleaseNote(): ReleaseNote {
  return RELEASE_NOTES[0];
}

const KEY = "antiek:release_notes_seen:v1";

export function hasSeenRelease(version: string): boolean {
  if (typeof window === "undefined") return false;
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return false;
    return (JSON.parse(raw) as string[]).includes(version);
  } catch {
    return false;
  }
}

export function markReleaseSeen(version: string): void {
  if (typeof window === "undefined") return;
  try {
    const raw = window.localStorage.getItem(KEY);
    const seen: string[] = raw ? (JSON.parse(raw) as string[]) : [];
    if (!seen.includes(version)) {
      window.localStorage.setItem(KEY, JSON.stringify([...seen, version]));
    }
  } catch {
    // Private mode — the note may re-show; harmless.
  }
}
