# interfaces/interview/

Interview capture web interface. DeepBlu lineage.

## Surface

A FastAPI app plus a small frontend (the minimum to capture voice +
text). Shareable links bring subjects to a capture page with:

- Voice recording (browser MediaRecorder API → upload to backend)
- Text fallback
- Optional structured prompts driven by a `skills/interview/` skill

## Flow

1. Operator creates an interview session, gets a shareable link.
2. Subject opens link, completes the interview.
3. Backend stores audio under `~/.antiek/interviews/` (content-addressed).
4. ASR + diarization run via `acquisition/interview/`.
5. Chunking + extraction + attribution run via `processing/` and
   `substrate/attribution/`.
6. The resulting nodes/edges land in the graph at `primary_interview`
   tier with proper consent and citation metadata.

## Deferred

The biography product layer — subscription, ads, revenue sharing — is
scaffolded but not implemented. See architecture_notes §5.
