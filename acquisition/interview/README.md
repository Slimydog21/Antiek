# acquisition/interview/

Interview capture (DeepBlu lineage). Voice and text.

## Pipeline

1. **Capture** — Subject hits a shareable link, provides voice or text
   responses. Voice is recorded to content-addressed storage at
   `~/.antiek/interviews/`.
2. **Transcription** — ASR via commercial Whisper API or equivalent.
   Do not roll our own.
3. **Diarization** — Commercial diarization service for multi-party
   interviews. Speaker attribution is non-trivial; the spec is explicit
   that we use a vendor here, not a homegrown implementation.
4. **Source tier** — Lands at `primary_interview` tier.
5. **Attribution** — Records consent, contribution scope, citation
   rights metadata. See `substrate/attribution/`.

## Output

Emits `capture_interview_response` events. Downstream processing
(chunking, embedding, extraction) is identical to other acquisition
paths once the chunk is emitted — see `processing/`.

## Out of scope here

The biography product layer (subscription flows, ads, revenue sharing)
is deferred. Capture works end-to-end; monetization does not ship in
this build. See architecture_notes §5.
