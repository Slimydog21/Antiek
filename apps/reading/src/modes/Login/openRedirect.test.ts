/**
 * GHSA-wrjc-x8rr-h8h6 — `?next=` reached `navigate()` unvalidated, so an
 * authenticated user could be redirected off-site. react-router patches this
 * in 7.18.0; this app is on 6.30.x, and the guarantee should not depend on the
 * router in any case.
 */
import { describe, expect, it } from "vitest";
import { internalPathOnly } from "./index";

describe("internalPathOnly", () => {
  it("rejects every off-site shape", () => {
    for (const hostile of [
      "https://evil.com",
      "//evil.com",
      "/\\evil.com",
      "\\\\evil.com",
      "\\/evil.com",
      "javascript:alert(1)",
      "https://antiek.ai.evil.com/login",
      "   https://evil.com",
    ]) {
      expect(internalPathOnly(hostile), `escaped via ${hostile}`).toBe("/");
    }
  });

  it("preserves real in-app destinations", () => {
    for (const ok of [
      "/",
      "/read/doc-1",
      "/inv/abc?tab=evidence",
      "/library#section",
      "/read/doc%20with%20space",
    ]) {
      expect(internalPathOnly(ok)).toBe(ok);
    }
  });
});
