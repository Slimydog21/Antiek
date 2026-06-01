# acquisition/youtube/

YouTube transcript ingestion for the owner's personal reading. Talks,
lectures, conference recordings, podcast video.

## ⚠️ ToS risk — operator-only, low-volume (read this first)

This connector's transcript-fetch path (`youtube-transcript-api` over
YouTube's unofficial `timedtext` endpoint) and its metadata path
(`yt-dlp`) **violates YouTube's Terms of Service regardless of personal
use.** The ToS prohibit accessing content other than through the public
interface or the official API; personal / non-commercial intent does
**not** cure that breach.

The Personal-Reading Lane (`content_class='personal_reading'`) cures the
*copyright-serving* problem — a scraped transcript is never served
publicly, never ad-attributed, never trained on. It does **not** cure
this *acquisition-ToS* problem. These are two separate legal questions
and only one of them is fixed by the lane.

The only ToS-clean caption path is the official `captions.download`
YouTube Data API, which is **owner-only** (you may only pull captions for
channels you own/manage). That is a larger auth project and is **out of
scope** here — see the open question below.

Because of the above, this connector is **operator-only and low-volume**
by design:

- A per-process fetch cap, `YOUTUBE_MAX_FETCHES_PER_RUN` (currently 25),
  enforced in-process via `note_youtube_fetch()`; exceeding it raises
  `YouTubeRateCapExceeded`. The cap is in-process only (no DB, no daemon,
  no queue) and resets per process, consistent with the §16 box-bounded /
  single-writer invariant.
- **No crawler, no channel fan-out, no playlist batch.** Ingest one
  explicitly-supplied video id/URL per call. The cap exists precisely to
  make a runaway loop or accidental batch fail loudly and early.

## Rights class (default and the one exception)

- **Default: `personal_reading`.** Owner-readable in full on the personal
  path; never served, monetized, or trained on.
- **Narrow exception:** pass `operator_confirmed_cc_by=True` to
  `ingest_youtube(...)` ONLY when you positively assert THIS specific
  video is published under CC-BY. Then the transcript is promoted to
  `source_declared_open` (servable) with a truthful `license_basis`
  recording the operator's per-video confirmation. The default Standard
  YouTube License is **not** CC-BY, so the safe state is the default.
- The CC-BY claim is about the *video's license*, not the caption
  provenance — an auto-captioned video can still be CC-BY.

## Caption provenance (auto vs human)

`YouTubeVideo.caption_kind` records `human | auto | unknown | missing`,
derived from the caption API's per-track `is_generated` flag — never
inferred or hardcoded. YouTube auto-captions (`auto`) are materially less
reliable than human/community captions (`human`); the reader is told the
truth. When the library cannot report generated-vs-manual for a track, the
value is recorded honestly as `unknown` — it is never defaulted to
`human`. The provenance round-trips into `documents.metadata.caption_kind`
and onto `IngestYouTubeResult.caption_kind`.

## Output

Writes a `documents` row + timestamped chunks + per-chunk nodes, and emits
a `document.loaded` event. `documents.metadata` carries:
- `video_id`, `channel`, `duration_seconds`
- `transcript_source` — `youtube` or `missing`
- `caption_kind` — `human | auto | unknown | missing`

## Open question (operator)

Should the owner-only official `captions.download` Data API later replace
this ToS-gray scrape path for videos on channels the operator controls?
That would make acquisition ToS-clean for owned channels but does nothing
for third-party videos, and is a larger auth project. Flagged, not built.

## Out of scope

Whisper re-transcription of the audio when captions are absent (the
no-transcript path simply skips); the ambient/monitoring feed (SPR-09);
switching to `captions.download` (above).
