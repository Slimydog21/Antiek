/**
 * What an ingest response means for every surface that reports one
 * (PasteIngest, StartResearch, the CreationStudio VoiceNoteCapture).
 *
 * The ingest routes answer `skipped` with `chunks_written: 0` whenever nothing
 * reached the graph: a paywalled or script-rendered page, a video without a
 * transcript, a passage too short to keep. No chunk was written, so nothing
 * from it can be cited, and the surface must not call it absorbed. The rule is
 * an allowlist: absorbed means the backend wrote chunks, or it resolved the
 * URL to a document already in the corpus. Any other answer, including a
 * status or skip reason this client does not know, is reported as not added.
 */

export interface IngestAnswer {
  status: string;
  chunks_written: number;
  skipped_reason: string | null;
  error_message?: string | null;
  title: string | null;
}

export type IngestVerdict =
  | { kind: "absorbed"; title: string }
  | { kind: "not_added"; why: string }
  | { kind: "failed"; reason: string | null };

const ALREADY_IN_CORPUS = "alias_resolved_to_existing_document";

// Plain words for the skip reasons the ingest adapters emit.
const SKIP_REASON_WORDS: Record<string, string> = {
  low_word_count: "there was too little readable text in it to keep",
  no_transcript: "it has no transcript to read",
  no_episodes_with_transcripts: "none of its episodes had a transcript to read",
  no_public_posts_ingested: "none of its posts were publicly readable",
  empty_thread: "the thread was empty",
};

export function ingestVerdict(r: IngestAnswer, fallbackTitle: string): IngestVerdict {
  const title = r.title ?? fallbackTitle;
  if (r.status === "error") {
    return { kind: "failed", reason: r.error_message ?? null };
  }
  if (r.status === "ingested" && r.chunks_written > 0) {
    return { kind: "absorbed", title };
  }
  if (r.status === "skipped" && r.skipped_reason === ALREADY_IN_CORPUS) {
    return { kind: "absorbed", title };
  }
  const because =
    (r.skipped_reason && SKIP_REASON_WORDS[r.skipped_reason]) ||
    "nothing readable came through";
  return {
    kind: "not_added",
    why: `Nothing from “${title}” was added: ${because}. It can’t be cited.`,
  };
}
