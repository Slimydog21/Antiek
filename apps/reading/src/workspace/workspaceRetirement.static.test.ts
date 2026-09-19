import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const source = (relative: string) => readFileSync(new URL(relative, import.meta.url), "utf8");

describe("workspace snapshot retirement static ratchets", () => {
  it("has no legacy snapshot API or layout writer", () => {
    const persistence = source("./persistence.ts");
    const store = source("./WorkspaceStore.ts");
    for (const retired of [
      "PersistedSnapshot",
      "buildShareableUrl",
      "readWsFromUrl",
      "encodeWsParam",
      "decodeWsParam",
      "writeScope",
      "setPersistScope",
    ]) {
      expect(`${persistence}\n${store}`).not.toContain(retired);
    }
    expect(store).not.toContain("localStorage");
    const boot = source("../main.tsx");
    const hydration = source("./useWorkspaceHydration.ts");
    expect(boot).toMatch(/retireLegacyWorkspaceSnapshots\(\);[\s\S]*createRoot/);
    expect(hydration).not.toMatch(/\n\s*retireLegacyWorkspaceSnapshots\(\);/);
  });

  it("has no share or storage-reset palette action", () => {
    const palette = source("../components/CommandPalette.tsx");
    expect(palette).not.toMatch(/shareable layout|[?&]ws=|clearScope|clearAll|localStorage/i);
    expect(palette).toContain("Reset current panel layout");
  });
});
