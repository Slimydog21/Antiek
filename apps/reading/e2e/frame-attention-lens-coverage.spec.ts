import { expect, test, type Page, type Route } from "@playwright/test";

import { installAuthMock } from "./_ams/auth";

interface FrameBatch {
  seconds: Array<{ lens: string; samples: Array<{ asset_id: string }> }>;
}

async function json(route: Route, body: unknown, status = 200): Promise<void> {
  await route.fulfill({
    status, contentType: "application/json",
    headers: { "access-control-allow-origin": "*" },
    body: JSON.stringify(body),
  });
}

async function houseFill(route: Route): Promise<void> {
  const request = route.request().postDataJSON() as
    | { window_id?: string; positions?: string[] }
    | null;
  if (!request?.window_id || !Array.isArray(request.positions)) {
    await json(route, { fills: [], served: false });
    return;
  }
  await json(route, {
    window_id: request.window_id,
    fills: request.positions.map((position) => ({
      fill_decision_id: `house:${position}`, slot_id: `slot:${position}`,
      position, kind: "house", ad: null, house: null,
      revenue_usd_cents: 0, price_status: "unpriced",
    })),
  });
}

async function captureFrames(page: Page): Promise<FrameBatch[]> {
  const batches: FrameBatch[] = [];
  await page.route("**/api/ad/fill*", houseFill);
  await page.route("**/api/ad/fills*", houseFill);
  await page.route("**/api/ad/frame-telemetry", async (route) => {
    batches.push(route.request().postDataJSON() as FrameBatch);
    await json(route, {}, 202);
  });
  return batches;
}

/** Boot the authed SPA under the fake clock. `loginAndGotoApp` is NOT usable
 *  here: its settle step is `page.waitForTimeout`, which never returns while
 *  `page.clock` owns the page's timers. Playwright's own polling (`expect`)
 *  does the waiting instead. */
async function gotoAuthed(page: Page, route: string): Promise<void> {
  await installAuthMock(page);
  await page.goto(route, { waitUntil: "domcontentloaded" });
}

/** `vite preview` proxies the `/write` API prefix, so a cold load of the SPA
 *  route `/write/:id` would hit the proxy instead of index.html. Boot at `/`
 *  and move to the route client-side, the way the app itself navigates. */
async function gotoAuthedClientSide(page: Page, route: string): Promise<void> {
  await gotoAuthed(page, "/");
  await expect(page.locator("#root > *").first()).toBeAttached();
  await page.evaluate((path) => {
    window.history.pushState({}, "", path);
    window.dispatchEvent(new PopStateEvent("popstate"));
  }, route);
}

async function expectSampledAsset(page: Page, batches: FrameBatch[], lens: string, assetId: string) {
  // A few real sampler ticks (1 Hz), then jump to the emitter's 30 s flush
  // ceiling. runFor(31_000) would replay ~1,900 animation frames of the
  // rAF-driven scene and blow the test budget; fastForward fires each due
  // timer once, which is exactly one more sample and the interval flush.
  await page.clock.runFor(3_000);
  await page.clock.fastForward(30_000);
  await expect.poll(() => batches.some((batch) =>
    batch.seconds.some((second) =>
      second.lens === lens && second.samples.some((sample) => sample.asset_id === assetId),
    ),
  )).toBe(true);
}

test("research lens: a servable named source earns a sampled second", async ({ page }) => {
  await page.clock.install();
  const batches = await captureFrames(page);
  const investigationId = "inv-e2e-frame";
  const chunkId = "chunk-e2e-research";
  const events = [
    {
      event_id: "event-start", action_type: "investigation.start_requested",
      emitted_at: "2026-01-01T00:00:00Z", payload: { question: "What changed?" },
    },
    {
      event_id: "event-synthesis", action_type: "synthesize.delivered",
      emitted_at: "2026-01-01T00:00:01Z",
      payload: {
        thesis_summary: "A measured finding.",
        thesis_components: [{
          claim: "The evidence supports this finding.", confidence: "high",
          effective_source_tier: 2, hedging_required: false,
          supporting_chunk_ids: [chunkId], supporting_path_indices: [],
        }],
        implicit_recommendation: "proceed",
      },
    },
    {
      event_id: "event-complete", action_type: "investigation.completed",
      emitted_at: "2026-01-01T00:00:02Z", payload: { thesis_summary: "A measured finding." },
    },
  ];
  await page.route(`**/trajectory/${investigationId}*`, (route) =>
    json(route, { investigation_id: investigationId, count: events.length, events }),
  );
  await page.route(`**/investigations/${investigationId}`, (route) =>
    json(route, { status: "completed", terminal_payload: null, source_policy: [] }),
  );
  await page.route("**/investigations?*", (route) =>
    json(route, { count: 0, investigations: [] }),
  );
  await page.route(`**/chunks/${chunkId}`, (route) => json(route, {
    chunk_id: chunkId, text: "Evidence from a servable source.", section_path: "p. 1",
    token_count: 8, document_id: "doc-e2e-research", document_title: "Research source",
    source_tier: 2, servable: true, servability: null,
  }));
  await page.route(`**/research/${investigationId}/distill`, (route) =>
    json(route, { insights: [], questions: [] }),
  );
  await page.route("**/research/suggestions*", (route) => json(route, { count: 0, suggestions: [] }));

  await gotoAuthed(page, `/inv/${investigationId}`);
  const source = page.getByRole("button", { name: /from Research source/ });
  await expect(source).toBeVisible();
  await source.scrollIntoViewIfNeeded();
  await expectSampledAsset(page, batches, "research", "doc-e2e-research");
});

test("write lens: a servable traced source earns a sampled second", async ({ page }) => {
  await page.clock.install();
  const batches = await captureFrames(page);
  const deliverableId = "deliverable-e2e-frame";
  const sectionId = "section-e2e-frame";
  const blockId = "block-e2e-frame";
  const nodeId = "a1b2c3d4e5f60718293a4b5c6d7e8f90";
  await page.route(`**/deliverables/${deliverableId}`, (route) => json(route, {
    deliverable_id: deliverableId, title: "A sourced draft", deliverable_kind: "general_essay",
    status: "draft", investigation_root_id: null,
    sections: [{
      section_id: sectionId, deliverable_id: deliverableId, parent_section_id: null,
      section_index: 0, title: "Finding", prose_text: "The evidence supports this paragraph.",
      prose_provenance: { "0": [nodeId] }, block_count: 1,
    }],
  }));
  await page.route(`**/write/sections/${sectionId}/blocks`, (route) => json(route, {
    blocks: [{
      outline_block_id: blockId, section_id: sectionId, block_kind: "insight",
      provenance_kind: "graph_node", node_id: nodeId, content: null,
      node_label: "The source finding", block_index: 0, is_user_originated: false,
    }],
  }));
  await page.route(`**/write/blocks/${blockId}/trace`, (route) => json(route, {
    kind: "document", full_text_allowed: true, document_id: "doc-e2e-write",
    document_title: "Write source", chunk_ids: ["chunk-e2e-write"],
    servability_status: "servable", detail: null,
  }));
  await page.route("**/write/folders", (route) => json(route, { folders: [] }));
  await page.route("**/write/blocks/search*", (route) => json(route, { hits: [] }));

  await gotoAuthedClientSide(page, `/write/${deliverableId}`);
  await page.getByRole("button", { name: "X-ray", exact: true }).click();
  await page.getByTestId("xray-paragraph-0").locator("button").first().click();
  await page.getByTestId("xray-paragraph-blocks-0").locator("button").first().click();
  const source = page.getByTestId("xray-block-uses").getByText("Source: Write source");
  await expect(source).toHaveText("Source: Write source");
  await source.scrollIntoViewIfNeeded();
  await expectSampledAsset(page, batches, "write", "doc-e2e-write");
});
