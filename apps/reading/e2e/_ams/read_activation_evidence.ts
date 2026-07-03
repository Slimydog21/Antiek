export type ReadActivationEvidenceDraftInput = {
  sessionId: string;
  date: string;
  buildSha: string;
  url: string;
  operator: string;
  documentId: string;
  entryDoor: string;
  visibleContentNote: string;
  selectedText: string;
  dialogueNoKeyCopy: string;
  researchNoKeyCopy: string;
  sourceDocumentId: string;
  chunkId: string;
  resultUrl: string;
  returnContextNote: string;
};

export type ReadActivationEvidenceDraft = {
  schema_version: 1;
  kind: "read_activation_record_session_draft";
  ready_to_append: false;
  reason_not_append_ready: string;
  operator_fields_to_replace: string[];
  record_session_fields_template: {
    session_id: string;
    date: string;
    build_sha: string;
    url: string;
    operator: string;
    document_id: string;
    entry_door: string;
    provider_status: "absent";
    live_provider_ai: false;
    citation_traced: true;
    minutes_reading: typeof PENDING_MINUTES;
    visible_content_note: string;
    selected_text: string;
    return_context_note: string;
    operator_note: typeof PENDING_OPERATOR_NOTE;
    dialogue_no_key_copy: string;
    research_no_key_copy: string;
    source_document_id: string;
    chunk_id: string;
    result_url: string;
  };
  observed_steps: {
    "1": string;
    "2": string;
    "3": string;
    "4": string;
    "5": string;
    "6": string;
    "7": string;
  };
  record_draft_argv_template: string[];
  record_draft_command_template: string;
  record_session_argv_template: string[];
  record_session_command_template: string;
};

const DRAFT_PATH = "<path_to_read_activation_record_session_draft.json>" as const;
const PENDING_MINUTES = "<minutes_reading_at_least_20>" as const;
const PENDING_OPERATOR_NOTE = "<operator_20_minute_reading_note>" as const;

export function buildReadActivationEvidenceDraft(
  input: ReadActivationEvidenceDraftInput,
): ReadActivationEvidenceDraft {
  const recordDraftArgv = [
    "antiek",
    "read",
    "activation",
    "record-draft",
    "--draft",
    DRAFT_PATH,
    "--minutes-reading",
    PENDING_MINUTES,
    "--operator-note",
    PENDING_OPERATOR_NOTE,
    "--operator",
    input.operator,
    "--session-id",
    input.sessionId,
  ];
  const recordSessionArgv = [
    "antiek",
    "read",
    "activation",
    "record-session",
    "--session-id",
    input.sessionId,
    "--date",
    input.date,
    "--build-sha",
    input.buildSha,
    "--url",
    input.url,
    "--operator",
    input.operator,
    "--document-id",
    input.documentId,
    "--entry-door",
    input.entryDoor,
    "--minutes-reading",
    PENDING_MINUTES,
    "--visible-content-note",
    input.visibleContentNote,
    "--selected-text",
    input.selectedText,
    "--return-context-note",
    input.returnContextNote,
    "--operator-note",
    PENDING_OPERATOR_NOTE,
    "--dialogue-no-key-copy",
    input.dialogueNoKeyCopy,
    "--research-no-key-copy",
    input.researchNoKeyCopy,
    "--citation-traced",
    "--source-document-id",
    input.sourceDocumentId,
    "--chunk-id",
    input.chunkId,
    "--result-url",
    input.resultUrl,
  ];
  const fields = {
    session_id: input.sessionId,
    date: input.date,
    build_sha: input.buildSha,
    url: input.url,
    operator: input.operator,
    document_id: input.documentId,
    entry_door: input.entryDoor,
    provider_status: "absent" as const,
    live_provider_ai: false as const,
    citation_traced: true as const,
    minutes_reading: PENDING_MINUTES,
    visible_content_note: input.visibleContentNote,
    selected_text: input.selectedText,
    return_context_note: input.returnContextNote,
    operator_note: PENDING_OPERATOR_NOTE,
    dialogue_no_key_copy: input.dialogueNoKeyCopy,
    research_no_key_copy: input.researchNoKeyCopy,
    source_document_id: input.sourceDocumentId,
    chunk_id: input.chunkId,
    result_url: input.resultUrl,
  };

  return {
    schema_version: 1,
    kind: "read_activation_record_session_draft",
    ready_to_append: false,
    reason_not_append_ready:
      "The real-route proxy proves golden-path steps 1-6 only. Step 7 requires an operator to read for at least 20 minutes and write the reading note before appending dogfood evidence.",
    operator_fields_to_replace: [PENDING_MINUTES, PENDING_OPERATOR_NOTE],
    record_session_fields_template: fields,
    observed_steps: {
      "1": input.visibleContentNote,
      "2": input.selectedText,
      "3": input.dialogueNoKeyCopy,
      "4": input.researchNoKeyCopy,
      "5": input.resultUrl,
      "6": input.returnContextNote,
      "7": "pending operator 20-minute dogfood note",
    },
    record_draft_argv_template: recordDraftArgv,
    record_draft_command_template: recordDraftArgv.map(shellQuote).join(" "),
    record_session_argv_template: recordSessionArgv,
    record_session_command_template: recordSessionArgv.map(shellQuote).join(" "),
  };
}

function shellQuote(value: string): string {
  if (/^[A-Za-z0-9_./:=@%+,~-]+$/.test(value)) {
    return value;
  }
  return `'${value.replace(/'/g, "'\\''")}'`;
}
