import type { Meta, StoryObj } from "@storybook/react";
import ConnectedToolSearch from "./ConnectedToolSearch";

function Mocked() {
  if (!(globalThis as { __antiekToolSearchMock?: boolean }).__antiekToolSearchMock) {
    const original = globalThis.fetch.bind(globalThis);
    globalThis.fetch = async (input, init) => {
      const url = String(input);
      if (url.endsWith("/settings/tools")) {
        return new Response(JSON.stringify({ connections: [{
          vendor: "youtube", display_name: "YouTube Data API", credential_kind: "api_key", auth: "api_key_query",
          docs_url: "https://console.cloud.google.com/apis/credentials", status: "configured_unverified",
          credential_present: true, status_note: null,
          quota: { kind: "youtube_units", remaining: 9600, limit: 10000, reset_at: "2026-08-13T07:00:00Z", hard_exhausted: false, note: "Provider remains authoritative" },
        }, {
          vendor: "x", display_name: "X Developer API", credential_kind: "api_key", auth: "bearer_token",
          docs_url: "https://developer.x.com/en/portal/dashboard", status: "configured_unverified",
          credential_present: true, status_note: null,
          quota: { kind: "rate_ceiling", remaining: null, limit: 25, reset_at: null, hard_exhausted: null, note: "25 per 15 minutes" },
        }], count: 2 }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      if (url.endsWith("/research/tools/search") && init?.method === "POST") {
        return new Response(JSON.stringify({ operation_id: "tool-search-123456789", vendor: "youtube", status: "completed", candidates: [
          { external_id: "a1", title_or_text: "Solid-state batteries: materials, interfaces, and manufacturing", url: "https://www.youtube.com/watch?v=a1", published_at: "2026-07-20T12:00:00Z", author: "Materials Institute" },
          { external_id: "b2", title_or_text: "Why sulfide electrolytes fail—and what recent research changes", url: "https://www.youtube.com/watch?v=b2", published_at: "2026-06-04T12:00:00Z", author: "Electrochemistry Lab" },
        ] }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      return original(input, init);
    };
    (globalThis as { __antiekToolSearchMock?: boolean }).__antiekToolSearchMock = true;
  }
  return <div className="min-h-screen bg-ice-1 p-6 dark:bg-charcoal-2"><div className="mx-auto max-w-3xl"><ConnectedToolSearch /></div></div>;
}

const meta = { title: "Sources/Connected tool search", component: Mocked } satisfies Meta<typeof Mocked>;
export default meta;
type Story = StoryObj<typeof meta>;
export const Ready: Story = {};
export const Narrow: Story = { parameters: { viewport: { defaultViewport: "mobile1" } } };
