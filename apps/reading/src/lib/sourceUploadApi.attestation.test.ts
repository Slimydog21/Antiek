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
  const capabilities: Array<[string, unknown]> = [
    ["null (route absent / error)", null],
    ["empty accepted", { accepted: [], authored_default: null, aliases: {} }],
    ["legacy-only accepted", { accepted: ["personal_reading", LEGACY_PUBLIC_TOKEN], authored_default: LEGACY_PUBLIC_TOKEN, aliases: {} }],
    ["alias only", { accepted: ["personal_reading"], authored_default: "user_authored_private", aliases: { [LEGACY_PUBLIC_TOKEN]: "user_authored_private" } }],
    ["A06-capable", { accepted: ["personal_reading", "user_authored_private", LEGACY_PUBLIC_TOKEN], authored_default: "user_authored_private", aliases: { [LEGACY_PUBLIC_TOKEN]: "user_authored_private" } }],
  ];

  it.each(capabilities)("authored with capability %s never maps to the legacy token", (_name, cap) => {
    let token: string | undefined;
    try {
      token = uploadApi.attestationToken("authored", cap as uploadApi.UploadAttestationCapability | null);
    } catch (error) {
      expect(error).toBeInstanceOf(uploadApi.SourceUploadError);
      expect((error as uploadApi.SourceUploadError).code).toBe("authored_unavailable");
    }
    expect(token).not.toBe(LEGACY_PUBLIC_TOKEN);
    if (token !== undefined) expect(token).toBe("user_authored_private");
  });

  it("maps authored to user_authored_private only when the API lists that exact token", () => {
    expect(uploadApi.attestationToken("authored", { accepted: ["personal_reading", "user_authored_private"], authored_default: "user_authored_private", aliases: {} })).toBe("user_authored_private");
    expect(() => uploadApi.attestationToken("authored", null)).toThrow(uploadApi.SourceUploadError);
    expect(() => uploadApi.attestationToken("authored", { accepted: ["personal_reading"], authored_default: "user_authored_private", aliases: {} })).toThrow(uploadApi.SourceUploadError);
  });

  it("maps personal reading to personal_reading regardless of capability (unchanged path)", () => {
    expect(uploadApi.attestationToken("personal", null)).toBe("personal_reading");
    expect(uploadApi.attestationToken("personal", { accepted: [], authored_default: null, aliases: {} })).toBe("personal_reading");
  });

  it("uploadSource refuses the legacy token at runtime without any request", async () => {
    apiFetchMock.mockReset();
    await expect(
      uploadApi.uploadSource(new File(["x"], "draft.md"), LEGACY_PUBLIC_TOKEN as uploadApi.AcquisitionAttestation),
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
