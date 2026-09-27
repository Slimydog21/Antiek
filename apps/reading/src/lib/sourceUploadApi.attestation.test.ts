/**
 * Private authored uploads never go out as the public legacy class (FFX
 * SPR-02, A-06 client half; backend INBOX 2026-09-27T00:40Z correction).
 *
 * On main, `user_owned` is projected to `platform_authored` and served
 * publicly (substrate/books/servability.py, substrate/constants.py), so an
 * authored draft uploaded under it is exposed. The client may send the
 * private authored token `user_authored_private` ONLY when the API
 * advertises it via GET /sources/upload/attestations; otherwise authored
 * upload is unavailable. There is no fallback to the legacy public token.
 */
import { readdirSync, readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { beforeEach, describe, expect, it, vi } from "vitest";

const apiFetchMock = vi.fn();
vi.mock("./api", () => ({
  API_BASE: "https://api.example.test",
  apiFetch: (...args: unknown[]) => apiFetchMock(...args),
}));

import * as uploadApi from "./sourceUploadApi";

// Built from parts so this test file does not itself match its own scan.
const LEGACY_PUBLIC_TOKEN = ["user", "owned"].join("_");

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

describe("attestation mapper (never yields the legacy public token)", () => {
  // Capability answers as the API would send them; null = the route 404s.
  const answers: Array<[string, unknown]> = [
    ["null (route absent / error)", null],
    ["empty accepted", { accepted: [], authored_default: null, aliases: {} }],
    ["legacy-only accepted", { accepted: ["personal_reading", LEGACY_PUBLIC_TOKEN], authored_default: LEGACY_PUBLIC_TOKEN, aliases: {} }],
    ["alias only", { accepted: ["personal_reading"], authored_default: "user_authored_private", aliases: { [LEGACY_PUBLIC_TOKEN]: "user_authored_private" } }],
    ["A06-capable", { accepted: ["personal_reading", "user_authored_private", LEGACY_PUBLIC_TOKEN], authored_default: "user_authored_private", aliases: { [LEGACY_PUBLIC_TOKEN]: "user_authored_private" } }],
  ];

  async function loadCapability(answer: unknown) {
    uploadApi.resetUploadAttestationsCache();
    apiFetchMock.mockReset();
    apiFetchMock.mockResolvedValueOnce(
      answer === null ? new Response("Not Found", { status: 404 }) : json(answer),
    );
    return uploadApi.loadUploadAttestations();
  }

  it.each(answers)("authored with capability %s never puts the legacy token on the wire", async (_name, answer) => {
    const cap = await loadCapability(answer);
    let attestation: uploadApi.AcquisitionAttestation | undefined;
    try {
      attestation = uploadApi.attestationToken("authored", cap);
    } catch (error) {
      expect(error).toBeInstanceOf(uploadApi.SourceUploadError);
      expect((error as uploadApi.SourceUploadError).code).toBe("authored_unavailable");
    }
    if (attestation === undefined) return;
    apiFetchMock.mockResolvedValueOnce(
      json({ document_id: "d", detected_kind: "md", reader_html_available: true, chunk_count: 0 }, 201),
    );
    await uploadApi.uploadSource(new File(["x"], "draft.md"), attestation);
    const form = (apiFetchMock.mock.calls.at(-1)![1] as RequestInit).body as FormData;
    expect(form.get("acquisition_attestation")).not.toBe(LEGACY_PUBLIC_TOKEN);
    expect(form.get("acquisition_attestation")).toBe("user_authored_private");
  });

  it("issues an authored attestation only when the API lists that exact token", async () => {
    expect(typeof uploadApi.attestationToken("authored", await loadCapability({ accepted: ["personal_reading", "user_authored_private"], authored_default: "user_authored_private", aliases: {} }))).toBe("object");
    expect(() => uploadApi.attestationToken("authored", null)).toThrow(uploadApi.SourceUploadError);
    const withoutToken = await loadCapability({ accepted: ["personal_reading"], authored_default: "user_authored_private", aliases: {} });
    expect(() => uploadApi.attestationToken("authored", withoutToken)).toThrow(uploadApi.SourceUploadError);
  });

  it("maps personal reading to personal_reading regardless of capability (unchanged path)", async () => {
    expect(uploadApi.attestationToken("personal", null)).toBe("personal_reading");
    expect(uploadApi.attestationToken("personal", await loadCapability({ accepted: [], authored_default: null, aliases: {} }))).toBe("personal_reading");
  });

  it("uploadSource refuses the legacy token at runtime without any request", async () => {
    apiFetchMock.mockReset();
    await expect(
      uploadApi.uploadSource(new File(["x"], "draft.md"), LEGACY_PUBLIC_TOKEN as unknown as uploadApi.AcquisitionAttestation),
    ).rejects.toMatchObject({ code: "authored_unavailable" });
    expect(apiFetchMock).not.toHaveBeenCalled();
  });
});

describe("capability route GET /sources/upload/attestations", () => {
  beforeEach(() => {
    apiFetchMock.mockReset();
    uploadApi.resetUploadAttestationsCache();
  });

  it("fetches once per session and reuses a successful answer", async () => {
    apiFetchMock.mockResolvedValue(json({ accepted: ["personal_reading", "user_authored_private"], authored_default: "user_authored_private", aliases: {} }));
    const a = await uploadApi.loadUploadAttestations();
    const b = await uploadApi.loadUploadAttestations();
    expect(a).toBe(b);
    expect(apiFetchMock).toHaveBeenCalledTimes(1);
    expect(apiFetchMock.mock.calls[0][0]).toBe("https://api.example.test/sources/upload/attestations");
    expect(uploadApi.authoredUploadSupported(a)).toBe(true);
  });

  it("resolves null on 404 or a network error and does not cache the failure", async () => {
    apiFetchMock.mockResolvedValueOnce(new Response("Not Found", { status: 404 }));
    expect(await uploadApi.loadUploadAttestations()).toBeNull();
    apiFetchMock.mockRejectedValueOnce(new TypeError("Failed to fetch"));
    expect(await uploadApi.loadUploadAttestations()).toBeNull();
    apiFetchMock.mockResolvedValueOnce(json({ unexpected: true }));
    expect(await uploadApi.loadUploadAttestations()).toBeNull();
    expect(apiFetchMock).toHaveBeenCalledTimes(3);
    expect(uploadApi.authoredUploadSupported(null)).toBe(false);
  });
});

describe("no code path can send the legacy public token for authored content", () => {
  // Scan the shipped (non-test) sources of the upload client and the Sources
  // mode. Comments are stripped first: block comments, and line comments whose
  // `//` starts a line or follows whitespace (so `https://` in a string is kept).
  const here = dirname(fileURLToPath(import.meta.url)); // apps/reading/src/lib
  const sourcesDir = resolve(here, "../modes/Sources");
  const files = [
    resolve(here, "sourceUploadApi.ts"),
    ...readdirSync(sourcesDir)
      .filter((f) => /\.(ts|tsx)$/.test(f) && !/\.test\.(ts|tsx)$/.test(f))
      .map((f) => join(sourcesDir, f)),
  ];
  const stripComments = (src: string) =>
    src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|\s)\/\/[^\n]*/g, "$1");

  it("scans a non-trivial file set", () => {
    expect(files.length).toBeGreaterThanOrEqual(2);
    expect(files.some((f) => f.endsWith("Sources/index.tsx"))).toBe(true);
  });

  it.each(files)("%s has no legacy public token outside comments", (file) => {
    const code = stripComments(readFileSync(file, "utf8"));
    expect(code.includes(LEGACY_PUBLIC_TOKEN), `${file} contains ${LEGACY_PUBLIC_TOKEN} in code`).toBe(false);
  });

  it("the comment stripper keeps string content and removes comments", () => {
    expect(stripComments('const u = "https://x"; // user_' + 'owned').trimEnd()).toBe('const u = "https://x";');
    expect(stripComments("/* " + LEGACY_PUBLIC_TOKEN + " */ const a = 1;")).toBe(" const a = 1;");
  });
});

describe("the authored token cannot leave without a verified capability (review R-01, R-02)", () => {
  const uploadCalls = () =>
    apiFetchMock.mock.calls.filter(([url]) => String(url).endsWith("/sources/upload"));
  const capabilityAnswer = (accepted: string[]) =>
    json({ accepted, authored_default: "user_authored_private", aliases: {} });

  beforeEach(() => {
    apiFetchMock.mockReset();
    uploadApi.resetUploadAttestationsCache();
  });

  it("a raw 'user_authored_private' string is refused before any request", async () => {
    await expect(
      // @ts-expect-error a raw string is not a verified authored attestation
      uploadApi.uploadSource(new File(["# Draft"], "draft.md"), "user_authored_private"),
    ).rejects.toMatchObject({ code: "authored_unavailable" });
    expect(apiFetchMock).not.toHaveBeenCalled();
  });

  it("after a 404 capability the raw string and the mapper both still refuse", async () => {
    apiFetchMock.mockResolvedValueOnce(new Response("Not Found", { status: 404 }));
    const cap = await uploadApi.loadUploadAttestations();
    expect(cap).toBeNull();
    expect(() => uploadApi.attestationToken("authored", cap)).toThrow(uploadApi.SourceUploadError);
    await expect(
      uploadApi.uploadSource(
        new File(["# Draft"], "draft.md"),
        "user_authored_private" as unknown as uploadApi.AcquisitionAttestation,
      ),
    ).rejects.toMatchObject({ code: "authored_unavailable" });
    expect(uploadCalls()).toHaveLength(0);
  });

  it("a hand-built capability object does not unlock the authored token", async () => {
    const forgedCapability = {
      accepted: ["personal_reading", "user_authored_private"],
      authored_default: "user_authored_private",
      aliases: {},
    } as unknown as uploadApi.UploadAttestationCapability;
    expect(uploadApi.authoredUploadSupported(forgedCapability)).toBe(false);
    expect(() => uploadApi.attestationToken("authored", forgedCapability)).toThrow(uploadApi.SourceUploadError);
    await expect(
      uploadApi.uploadSource(
        new File(["# Draft"], "draft.md"),
        {} as unknown as uploadApi.AcquisitionAttestation,
      ),
    ).rejects.toMatchObject({ code: "authored_unavailable" });
    expect(apiFetchMock).not.toHaveBeenCalled();
  });

  it("a verified capability yields an opaque value that uploadSource sends as the token", async () => {
    apiFetchMock.mockResolvedValueOnce(capabilityAnswer(["personal_reading", "user_authored_private"]));
    const cap = await uploadApi.loadUploadAttestations();
    const attestation = uploadApi.attestationToken("authored", cap);
    expect(typeof attestation).not.toBe("string");
    apiFetchMock.mockResolvedValueOnce(
      json({ document_id: "doc-upload-1", detected_kind: "md", reader_html_available: true, chunk_count: 0 }, 201),
    );
    await uploadApi.uploadSource(new File(["# Draft"], "draft.md"), attestation);
    expect(uploadCalls()).toHaveLength(1);
    const form = (uploadCalls()[0][1] as RequestInit).body as FormData;
    expect(form.get("acquisition_attestation")).toBe("user_authored_private");
  });

  it("the loaded capability is frozen, so a consumer cannot fake the advertisement", async () => {
    apiFetchMock.mockResolvedValueOnce(capabilityAnswer(["personal_reading"]));
    const cap = await uploadApi.loadUploadAttestations();
    expect(cap).not.toBeNull();
    expect(Object.isFrozen(cap)).toBe(true);
    expect(Object.isFrozen(cap!.accepted)).toBe(true);
    expect(() => (cap!.accepted as string[]).push("user_authored_private")).toThrow(TypeError);
    expect(uploadApi.authoredUploadSupported(cap)).toBe(false);
    expect(() => uploadApi.attestationToken("authored", cap)).toThrow(uploadApi.SourceUploadError);
  });
});
