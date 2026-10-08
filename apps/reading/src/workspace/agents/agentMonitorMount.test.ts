/**
 * agentMonitorMount.test.ts — SPR-10 M6: AppShell mounts the two entry-safe
 * shells once; the shells pull nothing lazy; only AgentMonitorFeed imports
 * the pre-backend adapter; nothing under agents/ publishes the tree.
 */
import { readFileSync, readdirSync } from "node:fs";
import { join, resolve } from "node:path";
import { describe, expect, it } from "vitest";

const here = typeof __dirname === "string" ? __dirname : resolve(process.cwd(), "src/workspace/agents");
const read = (rel: string) => readFileSync(resolve(here, rel), "utf8");
const specs = (src: string) => [...src.matchAll(/^\s*import\s+(?:type\s+)?[\s\S]*?from\s+["']([^"']+)["'];?\s*$/gm)].map((m) => m[1]);
const valueSpecs = (src: string) => [...src.matchAll(/^\s*import\s+(?!type\s)[\s\S]*?from\s+["']([^"']+)["'];?\s*$/gm)].map((m) => m[1]);

describe("AppShell mounts", () => {
  const shell = read("../../AppShell.tsx");
  it("mounts <AgentMonitor /> and <AgentGoto /> exactly once, beside the toast viewport", () => {
    expect(shell.match(/<AgentMonitor \/>/g)).toHaveLength(1);
    expect(shell.match(/<AgentGoto \/>/g)).toHaveLength(1);
    expect(shell).toMatch(/import \{ AgentMonitor \} from "\.\/workspace\/agents\/AgentMonitor";/);
    expect(shell).toMatch(/import \{ AgentGoto \} from "\.\/workspace\/agents\/AgentGoto";/);
  });
});

describe("entry-safe shells", () => {
  const LAZY = /agentStatusStore|statusToasts|companionStore|contracts\/(treeStore|adapters|selection|index)|zustand|pollingAdapter|focusAgent|AgentGotoContent|AgentMonitorFeed/;
  for (const f of ["AgentMonitor.tsx", "AgentGoto.tsx", "statusToastFlag.ts"]) {
    it(`${f} statically imports nothing lazy`, () => {
      const hits = valueSpecs(read(f)).filter((s) => LAZY.test(s));
      expect(hits).toEqual([]);
    });
  }
  it("statusToastFlag.ts has no imports at all", () => {
    expect(specs(read("statusToastFlag.ts"))).toEqual([]);
  });
});

describe("the adapter and the write path", () => {
  const files = readdirSync(here).filter((f) => /\.(ts|tsx)$/.test(f) && !/\.(test|stories)\./.test(f));
  it("only AgentMonitorFeed.tsx imports contracts/adapters/preBackend", () => {
    const importers = files.filter((f) => /contracts\/adapters\/preBackend/.test(read(f)));
    expect(importers).toEqual(["AgentMonitorFeed.tsx"]);
  });
  it("nothing under agents/ names publishTree or writes AgentNode.status", () => {
    for (const f of files) {
      expect(read(f), f).not.toMatch(/\bpublishTree\s*\(/);
      expect(read(f), f).not.toMatch(/\.status\s*=\s/);
    }
  });
  it("AgentMonitorFeed mounts the ONE <PreBackendTreeFeed investigationLimit={50} /> line behind feedTree", () => {
    const src = read("AgentMonitorFeed.tsx");
    expect(src.match(/<PreBackendTreeFeed investigationLimit=\{50\} \/>/g)).toHaveLength(1);
    expect(src).toMatch(/feedTree/);
  });
});
