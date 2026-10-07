/**
 * intakeKinds.ts — what the zen home's box accepts, as one table
 * (FFX-KPA SPR-03 M3). The SPR-B lane adds image / PDF / docx routes here
 * without reading the sprint page.
 *
 * | kind        | matched by                              | route today                 | body                    | failure copy                         | test                         |
 * |-------------|-----------------------------------------|-----------------------------|-------------------------|--------------------------------------|------------------------------|
 * | text-file   | .txt .md .markdown .csv .json .log .rtf  | POST /voice-notes/ingest    | {transcript, title}     | "Couldn’t absorb that" + server body | ZenHome.test "text file"     |
 * |             | or a text/* MIME                        |                             |                         |                                      |                              |
 * | url         | a bare http(s) URL (dropped or typed)   | POST /sources/ingest        | {url}                   | ingest error_message                 | ZenHome.test "url"           |
 * | image       | image/* or .png .jpg .jpeg .gif .webp    | refused until SPR-B intake  | — never uploaded        | REFUSED_UNTIL_INTAKE_COPY            | ZenHome.test "refused kinds" |
 * |             | .heic .svg                               |                             |                         |                                      |                              |
 * | pdf         | application/pdf or .pdf                 | refused until SPR-B intake  | — never uploaded        | REFUSED_UNTIL_INTAKE_COPY            | ZenHome.test "refused kinds" |
 * | docx        | .docx / .doc or the Word MIME types     | refused until SPR-B intake  | — never uploaded        | REFUSED_UNTIL_INTAKE_COPY            | ZenHome.test "refused kinds" |
 * | unsupported | anything else                           | refused                     | — never uploaded        | UNSUPPORTED_COPY                     | ZenHome.test "refused kinds" |
 *
 * To light up images and documents: set INTAKE_CONTRACT to
 * `{ live: true, route: "<the route SPR-B publishes>" }` and teach
 * useProjectIntake to send the file there. `acceptanceFor` refuses while the
 * route is null even if `live` is true, so nothing is ever sent to a guessed
 * endpoint. Refused files are never held, read or turned into blob URLs.
 */

export type IntakeKind = "text-file" | "url" | "image" | "pdf" | "docx" | "unsupported";

export interface IntakeContract {
  live: boolean;
  route: string | null;
}

/** TODO(ffx-nav-backend-intake, SPR-B): the receiving contract for
 *  image / PDF / docx project seeds. Off until the backend publishes it. */
export const INTAKE_CONTRACT: IntakeContract = { live: false, route: null };

/** Inherited cap: refs/agent-pane-refs.md §1 (Grok composer, six attachments). */
export const MAX_ATTACHMENTS = 6;

export const REFUSED_UNTIL_INTAKE_COPY =
  "Images and documents arrive once the intake lands; paste the text for now.";
export const UNSUPPORTED_COPY = "That kind of file can’t be absorbed yet. Paste a link to it, or paste its text.";
export const CAP_COPY = `Six attachments at most. Remove one to add another.`;

type Row =
  | { kind: "text-file" | "url"; route: string; refusedCopy?: undefined }
  | { kind: "image" | "pdf" | "docx"; route: "intake-contract"; refusedCopy: string }
  | { kind: "unsupported"; route: null; refusedCopy: string };

export const INTAKE_KINDS: readonly Row[] = [
  { kind: "text-file", route: "POST /voice-notes/ingest" },
  { kind: "url", route: "POST /sources/ingest" },
  { kind: "image", route: "intake-contract", refusedCopy: REFUSED_UNTIL_INTAKE_COPY },
  { kind: "pdf", route: "intake-contract", refusedCopy: REFUSED_UNTIL_INTAKE_COPY },
  { kind: "docx", route: "intake-contract", refusedCopy: REFUSED_UNTIL_INTAKE_COPY },
  { kind: "unsupported", route: null, refusedCopy: UNSUPPORTED_COPY },
];

const TEXT_EXT = /\.(txt|md|markdown|csv|json|log|rtf)$/i;
const IMAGE_EXT = /\.(png|jpe?g|gif|webp|heic|svg)$/i;
const DOCX_EXT = /\.docx?$/i;
const DOCX_MIME = new Set([
  "application/msword",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
]);
const URL_RE = /^https?:\/\/\S+$/i;

export function classifyFile(file: Pick<File, "name" | "type">): IntakeKind {
  const { name, type } = file;
  if (TEXT_EXT.test(name) || type.startsWith("text/")) return "text-file";
  if (type.startsWith("image/") || IMAGE_EXT.test(name)) return "image";
  if (type === "application/pdf" || /\.pdf$/i.test(name)) return "pdf";
  if (DOCX_MIME.has(type) || DOCX_EXT.test(name)) return "docx";
  return "unsupported";
}

/** A dropped or typed string is a URL attachment only when it is a bare URL. */
export function classifyText(text: string): "url" | null {
  return URL_RE.test(text.trim()) ? "url" : null;
}

export type Acceptance = { accepted: true; route: string } | { accepted: false; copy: string };

export function acceptanceFor(kind: IntakeKind, contract: IntakeContract = INTAKE_CONTRACT): Acceptance {
  const row = INTAKE_KINDS.find((r) => r.kind === kind);
  if (!row) return { accepted: false, copy: UNSUPPORTED_COPY };
  switch (row.kind) {
    case "text-file":
    case "url":
      return { accepted: true, route: row.route };
    case "unsupported":
      return { accepted: false, copy: row.refusedCopy };
    default:
      return contract.live && contract.route
        ? { accepted: true, route: contract.route }
        : { accepted: false, copy: row.refusedCopy };
  }
}
