import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

import LinkMonster from "./LinkMonster";
import {
  MonsterError,
  feedMonster,
  getMonsterStats,
  listMonsterFeed,
} from "../../api/linkMonster";

// The p5 sketch is canvas work — jsdom has no canvas; mock the module
// so the page still exercises its DOM + state logic.
vi.mock("p5", () => {
  class MockP5 {
    constructor(sketch: (p: unknown) => void, _el?: unknown) {
      // Run setup if the sketch defines one.
      const p = {
        createCanvas: () => ({ style: () => {} }),
        windowWidth: 800,
        windowHeight: 600,
        noLoop: () => {},
      };
      sketch(p as never);
      if (typeof (p as never as { setup?: () => void }).setup === "function") {
        (p as never as { setup: () => void }).setup();
      }
    }
    remove() {}
  }
  return { default: MockP5 };
});

vi.mock("./monsterSketch", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./monsterSketch")>();
  return {
    ...actual,
    createMonsterSketch: () => ({
      sketch: () => {},
      handle: {
        feed: vi.fn(),
        absorb: vi.fn(),
        leftover: vi.fn(),
        reset: vi.fn(),
      },
    }),
  };
});

vi.mock("../../api/linkMonster", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/linkMonster")>();
  return {
    ...actual,
    listMonsterFeed: vi.fn(),
    getMonsterStats: vi.fn(),
    feedMonster: vi.fn(),
  };
});

const mealDigest = {
  url: "https://example.com/post/1",
  final_url: "https://example.com/post/1",
  platform: "generic" as const,
  platform_label: "Web",
  title: "The Monster Test Post",
  author: "Jane Researcher",
  author_url: null,
  published_at: "2026-08-01T12:00:00+00:00",
  description: "A digest description",
  site_name: "Example Site",
  thumbnail_url: "https://img.example.com/cover.jpg",
  image_urls: ["https://img.example.com/cover.jpg"],
  video: null,
  transcript: null,
  text: { markdown: "# t", chars: 230, word_count: 38, source: "dom" },
  provenance: { title: "og", text: "dom" },
  outcome: "meal" as const,
  artifacts: { images: 1, videos: 0, transcript_chars: 0, text_chars: 230, body_chars: 230 },
  digested_at: "2026-08-13T10:00:00+00:00",
};


// jsdom has no matchMedia; stub it the same way the rest of the app's
// tests do (usePrefersReducedMotion reads it).
beforeEach(() => {
  if (!window.matchMedia) {
    Object.defineProperty(window, "matchMedia", {
      writable: true,
      value: (query: string) => ({
        matches: false,
        media: query,
        onchange: null,
        addListener: () => {},
        removeListener: () => {},
        addEventListener: () => {},
        removeEventListener: () => {},
        dispatchEvent: () => false,
      }),
    });
  }
});

beforeEach(() => {
  vi.mocked(listMonsterFeed).mockResolvedValue([]);
  vi.mocked(getMonsterStats).mockResolvedValue({
    meals: 0, snacks: 0, total: 0, chunks: 0, nodes: 0, edges: 0,
    by_platform: {}, last_digested_at: null,
  });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("LinkMonster page", () => {
  it("renders the furnace stage chrome", async () => {
    render(<LinkMonster />);
    expect(screen.getByText("LINK MONSTER")).toBeTruthy();
    expect(screen.getByLabelText("Link to feed")).toBeTruthy();
    expect(screen.getByRole("button", { name: "FEED IT" })).toBeTruthy();
    await waitFor(() => expect(screen.getByText("nothing eaten yet. feed it a link.")).toBeTruthy());
  });

  it("rejects a non-URL with a leftover banner", async () => {
    render(<LinkMonster />);
    const input = screen.getByLabelText("Link to feed");
    fireEvent.change(input, { target: { value: "not a url" } });
    fireEvent.click(screen.getByRole("button", { name: "FEED IT" }));
    await waitFor(() =>
      expect(screen.getByRole("alert").textContent).toContain("That is not a link"),
    );
    expect(feedMonster).not.toHaveBeenCalled();
  });

  it("feeds a URL and lands the meal in the menu", async () => {
    vi.mocked(feedMonster).mockResolvedValue({
      ok: true,
      document_id: "doc-lm-abc",
      already_digested: false,
      digest: mealDigest,
      store: { chunks_written: 3, node_ids: [], edge_ids: [], content_class: "personal_reading", already_digested: false },
    });
    vi.mocked(listMonsterFeed).mockResolvedValue([
      {
        document_id: "doc-lm-abc",
        title: "The Monster Test Post",
        author: "Jane Researcher",
        source_uri: "https://example.com/post/1",
        acquired_at: "2026-08-13T10:00:00+00:00",
        digest: mealDigest,
      },
    ]);
    render(<LinkMonster />);
    const input = screen.getByLabelText("Link to feed");
    fireEvent.change(input, { target: { value: "https://example.com/post/1" } });
    fireEvent.click(screen.getByRole("button", { name: "FEED IT" }));
    await waitFor(() => expect(feedMonster).toHaveBeenCalledWith("https://example.com/post/1"));
    await waitFor(() => expect(screen.getByText("The Monster Test Post")).toBeTruthy());
  });

  it("surfaces a typed Monster error as a leftover", async () => {
    vi.mocked(feedMonster).mockRejectedValue(
      new MonsterError("ssrf_blocked", "refused to fetch ssrf_blocked", 422),
    );
    render(<LinkMonster />);
    const input = screen.getByLabelText("Link to feed");
    fireEvent.change(input, { target: { value: "http://127.0.0.1:8001/health" } });
    fireEvent.click(screen.getByRole("button", { name: "FEED IT" }));
    await waitFor(() =>
      expect(screen.getByRole("alert").textContent).toContain("refused to fetch"),
    );
  });
});
