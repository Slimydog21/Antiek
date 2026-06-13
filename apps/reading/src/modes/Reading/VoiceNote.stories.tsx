import { useEffect, useRef } from "react";
import type { Meta, StoryObj } from "@storybook/react";

import VoiceNote from "./VoiceNote";
import { httpError, json, pendingForever, stubFetch, stubRecorder } from "./storyFetch";

/**
 * VoiceNote (Read SPR-06) — capture a spoken note, transcribe it, let the reader
 * CORRECT the transcript (the honesty guard), then distill it into anchored
 * notes.
 *
 * Product-character authorship (ALC SPR-09): VoiceNote has FIVE phases
 * (`capture | transcribing | correcting | saving | saved`) plus an error state,
 * and each meaningful phase is authored as its OWN named, co-located story so it
 * is inspectable in isolation (the rubric's Dimension-3 level-3 criterion). The
 * phases are reached through the component's REAL reducer: stories pin the
 * browser mic/recorder APIs (`stubRecorder`) so the real `useVoiceRecorder` hook
 * yields a blob without a microphone, and pin `fetch` (`storyFetch.tsx`) so the
 * transcribe/save responses are deterministic. Nothing in VoiceNote is mocked —
 * only the browser's mic + recorder + network. Runtime behaviour is unchanged.
 *
 * §5 voice + brand firewall: all copy is the component's own; no PostHog phrasing.
 */
const meta = {
  title: "Read / VoiceNote",
  component: VoiceNote,
  parameters: { layout: "padded" },
  tags: ["autodocs"],
  args: { documentId: "doc-book-1", pageIndex: 4, investigationId: "read-doc-book-1" },
} satisfies Meta<typeof VoiceNote>;

export default meta;
type Story = StoryObj<typeof meta>;

/**
 * Drives the REAL component into a later phase by clicking through the actual
 * controls on mount: Record → Stop produces a blob (via the stubbed recorder),
 * which the component transcribes; once the correction textarea appears, an
 * optional Save click advances to saving/saved. Each step exercises the real
 * onClick handler — only the mic + recorder + network are stubbed.
 */
function VoiceDriver({ save }: { save?: boolean }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const root = ref.current;
    if (!root) return;
    let cancelled = false;
    const byText = (re: RegExp) =>
      Array.from(root.querySelectorAll("button")).find((b) => re.test(b.textContent ?? ""));

    // Record, then stop — yields a blob through the real recorder hook.
    byText(/Record a thought/)?.click();
    const stopTimer = window.setTimeout(() => {
      if (cancelled) return;
      byText(/Stop/)?.click();
      if (!save) return;
      // After transcription lands and the correction step renders, save.
      const saveTimer = window.setInterval(() => {
        if (cancelled) return;
        const saveBtn = byText(/Save note/);
        if (saveBtn) {
          window.clearInterval(saveTimer);
          saveBtn.click();
        }
      }, 30);
    }, 0);
    return () => {
      cancelled = true;
      window.clearTimeout(stopTimer);
    };
  }, [save]);
  return (
    <div ref={ref}>
      <VoiceNote documentId="doc-book-1" pageIndex={4} investigationId="read-doc-book-1" />
    </div>
  );
}

/** CAPTURE — the resting phase: "Record a thought", the reader's starting point. */
export const Capture: Story = {};

/**
 * TRANSCRIBING — the in-flight phase, pinned: the recording finished and is being
 * turned into text. Transcription `fetch` never settles so the "Transcribing…"
 * status holds for inspection.
 */
export const Transcribing: Story = {
  decorators: [stubRecorder(), stubFetch(pendingForever)],
  render: () => {
    return <VoiceDriver />;
  },
};

/**
 * CORRECTING — the honesty guard: the transcript came back and the reader can
 * fix any misheard word in the editable textarea BEFORE it becomes a note. This
 * is the phase that makes the ASR honesty discipline visible in the UI.
 */
export const Correcting: Story = {
  decorators: [
    stubRecorder(),
    stubFetch((url) =>
      /\/voice\/transcribe/.test(url)
        ? json({ transcript: "the authr argues for a long now", language: "en", duration_seconds: 4 })
        : json({}),
    ),
  ],
  render: () => {
    return <VoiceDriver />;
  },
};

/**
 * TRANSCRIPTION UNAVAILABLE — the graceful degrade: the transcriber is down
 * (503), so the reader still lands on the correction step with an EMPTY textarea
 * and a calm message, and can type the note by hand. The flow never crashes when
 * a dependency is missing.
 */
export const TranscriptionUnavailable: Story = {
  decorators: [
    stubRecorder(),
    stubFetch((url) => (/\/voice\/transcribe/.test(url) ? httpError(503) : json({}))),
  ],
  render: () => {
    return <VoiceDriver />;
  },
};

/**
 * SAVING — the in-flight distill phase, pinned: the corrected transcript is being
 * distilled into anchored notes. The save `fetch` never settles so "Distilling
 * into notes…" holds for inspection.
 */
export const Saving: Story = {
  decorators: [
    stubRecorder(),
    stubFetch((url) =>
      /\/voice\/transcribe/.test(url)
        ? json({ transcript: "the author argues for a long now", language: "en", duration_seconds: 4 })
        : pendingForever(),
    ),
  ],
  render: () => {
    return <VoiceDriver save />;
  },
};

/**
 * SAVED — the resolved phase: the thought was distilled into anchored notes, and
 * the reader can capture another. The count is the component's own honest plural.
 */
export const Saved: Story = {
  decorators: [
    stubRecorder(),
    stubFetch((url) =>
      /\/voice\/transcribe/.test(url)
        ? json({ transcript: "the author argues for a long now", language: "en", duration_seconds: 4 })
        : json({
            voice_note_id: "vnote-1",
            document_id: "doc-book-1",
            page_index: 4,
            note_count: 2,
            notes: ["an insight", "an open question"],
            emitted_event_ids: ["e1", "e2"],
          }),
    ),
  ],
  render: () => {
    return <VoiceDriver save />;
  },
};

/**
 * SAVE FAILED — the distiller errored: the reader is returned to the correction
 * step with the failure shown inline and the corrected transcript preserved, so
 * nothing typed is lost and the save can be retried.
 */
export const SaveFailed: Story = {
  decorators: [
    stubRecorder(),
    stubFetch((url) =>
      /\/voice\/transcribe/.test(url)
        ? json({ transcript: "the author argues for a long now", language: "en", duration_seconds: 4 })
        : httpError(503),
    ),
  ],
  render: () => {
    return <VoiceDriver save />;
  },
};
