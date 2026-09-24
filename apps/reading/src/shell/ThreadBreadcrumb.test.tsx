/**
 * ThreadBreadcrumb.test — the integrity warning is a sentence, set in sans.
 *
 * Design spec §3 (audit T5): mono never carries an error sentence. A forked
 * thread (a workflow holding a copy instead of the one entity) suppresses the
 * trail and says so in a role=alert line, which was 12px JetBrains Mono.
 */
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

import { ThreadBreadcrumb } from "./ThreadBreadcrumb";
import type { Thread, ThreadHop } from "./threadModel";

afterEach(cleanup);

const hop = (workflow: ThreadHop["workflow"], entityId: string): ThreadHop => ({
  workflow,
  entityId,
  entityKind: "investigation",
  seamEventId: null,
  seamActionType: null,
  provenanceRef: null,
  built: true,
  viaProvisionalSeam: false,
});

describe("ThreadBreadcrumb integrity warning", () => {
  it("names the fork in the interface face, not mono", () => {
    const thread: Thread = {
      canonicalEntityId: "inv-1",
      canonicalEntityKind: "investigation",
      hops: [hop("research", "inv-1"), hop("write", "inv-1-copy")],
      stubs: [],
      isDegenerate: false,
    };
    render(<ThreadBreadcrumb thread={thread} />);
    const alert = screen.getByRole("alert");
    expect(alert.textContent).toContain("inv-1-copy");
    expect(alert.className).not.toMatch(/\bfont-mono\b/);
  });
});
