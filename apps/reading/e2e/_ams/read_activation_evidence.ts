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
  observed_steps: {
    "1": string;
    "2": string;
    "3": string;
    "4": string;
    "5": string;
    "6": string;
    "7": string;
  };
  record_session_argv_template: string[];
  record_session_command_template: string;
};

const PENDING_MINUTES = "<minutes_reading_at_least_20>";
const PENDING_OPERATOR_NOTE = "<operator_20_minute_reading_note>";

export function buildReadActivationEvidenceDraft(
  input: ReadActivationEvidenceDraftInput,
): ReadActivationEvidenceDraft {
  const argv = [
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

  return {
    schema_version: 1,
    kind: "read_activation_record_session_draft",
    ready_to_append: false,
    reason_not_append_ready:
      "The real-route proxy proves golden-path steps 1-6 only. Step 7 requires an operator to read for at least 20 minutes and write the reading note before appending dogfood evidence.",
    operator_fields_to_replace: [PENDING_MINUTES, PENDING_OPERATOR_NOTE],
    observed_steps: {
      "1": input.visibleContentNote,
      "2": input.selectedText,
      "3": input.dialogueNoKeyCopy,
      "4": input.researchNoKeyCopy,
      "5": input.resultUrl,
      "6": input.returnContextNote,
      "7": "pending operator 20-minute dogfood note",
    },
    record_session_argv_template: argv,
    record_session_command_template: argv.map(shellQuote).join(" "),
  };
}

function shellQuote(value: string): string {
  if (/^[A-Za-z0-9_./:=@%+,~-]+$/.test(value)) {
    return value;
  }
  return `'${value.replace(/'/g, "'\\''")}'`;
}
