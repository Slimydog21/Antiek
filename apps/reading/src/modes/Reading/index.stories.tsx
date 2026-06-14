import { MemoryRouter, Route, Routes } from "react-router-dom";
import type { Meta, StoryObj } from "@storybook/react";

import BookReader from "./index";
import { httpError, json, pendingForever, stubFetch } from "./storyFetch";
import type { BookDetail, FullTextResponse } from "../../api/books";

/**
 * BookReader (Read SPR-03..08) — the Reading SHELL: the composition root that
 * mounts the whole reading surface (TOC, reading column, ad rails, the float
 * menu, the reading companion, the talk-to-book bookmark, voice-note + spin-
 * research actions). Most of its surface is its CHILDREN's states (each of which
 * is now storied in its own co-located file).
 *
 * Product-character authorship (ALC SPR-09): the brief asks an honest question —
 * is this a pure router with no states of its own (document-exclude it), or does
 * it author meaningful TOP-LEVEL states (story those)? The honest answer is the
 * SECOND: BookReader authors several states of its OWN, before and around its
 * children, via its `loading` / `error` branches (`CenterNote`, §5 copy from
 * `READING_STATE_COPY`) and its rights-tiered render branch:
 *   • OPENING — its own live-region loading note ("Opening the book…");
 *   • NOT FOUND — its own §5 "that book isn't in the library" alert;
 *   • ERROR — its own calm catch-all alert (never the raw engine string);
 *   • LINK-BACK — the arXiv T2/T3 branch (no hosted body, no ad rails);
 *   • PREVIEW-ONLY / REMOVED — its own gated/taken-down body notices.
 * So it is NOT document-excluded; these own-states are authored here as named,
 * co-located stories, reached through the component's REAL data path (each story
 * pins `fetch` so `getBook` + `getBookFullText` drive the branch). The full
 * hosted-body composition is also shown so the shell's resolved state is
 * inspectable. Nothing is mocked — only the network. Runtime behaviour unchanged.
 *
 * §5 voice + brand firewall: the state copy is `READING_STATE_COPY`; no PostHog
 * phrasing. The shell mounts a router via its own `MemoryRouter` (opting out of
 * the global one) so its real `useParams` supplies the `:documentId`.
 */
const DOC = "doc-book-1";

const meta = {
  title: "Read / BookReader (shell)",
  component: BookReader,
  parameters: { layout: "fullscreen" },
  tags: ["autodocs"],
} satisfies Meta<typeof BookReader>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Mount the shell at a real route so its `useParams` resolves `:documentId`. */
function ReaderAt() {
  return (
    <MemoryRouter initialEntries={[`/read/${DOC}`]}>
      <Routes>
        <Route path="/read/:documentId" element={<BookReader />} />
      </Routes>
    </MemoryRouter>
  );
}

/** A BookDetail in the shape `getBook` returns. */
function detail(over: Partial<BookDetail> = {}): BookDetail {
  return {
    document_id: DOC,
    title: "The Order of Time",
    author: "C. Rovelli",
    servability: "public_domain",
    servable_full_text: true,
    page_count: 3,
    cover_uri: null,
    ip_holder_id: null,
    taken_down: false,
    pagination_scheme: "tokens",
    provenance: null,
    license_basis: null,
    toc: [{ title: "Chapter 1", page_index: 0, level: 1 }],
    ...over,
  };
}

/** A FullTextResponse in the shape `getBookFullText` returns. */
function fullText(over: Partial<FullTextResponse> = {}): FullTextResponse {
  return {
    document_id: DOC,
    servable: true,
    servability: "public_domain",
    full_text:
      "Time is not what it seems. The order of past and future is not fundamental; it emerges from a special state of the world. What we call the flow of time is the reading of this gradient by creatures made of memory and expectation.",
    snippet: null,
    title: "The Order of Time",
    author: "C. Rovelli",
    reason: "servable",
    tier: null,
    ad_eligible: true,
    canonical_url: null,
    license: null,
    ...over,
  };
}

/**
 * OPENING — the shell's OWN loading state: while `getBook` + `getBookFullText`
 * are in flight, the shell shows its calm live-region "Opening the book…" note on
 * the same procedural background the reader already sees. Pinned (both fetches
 * never settle) so the transient state holds for inspection.
 */
export const Opening: Story = {
  parameters: { router: false },
  decorators: [stubFetch(pendingForever)],
  render: () => {
    return <ReaderAt />;
  },
};

/**
 * NOT FOUND — the shell's OWN known-failure state: the book isn't in the library.
 * `getBook` answers 404, the client maps it to `book_not_found`, and the shell
 * shows its §5 "that book isn't in the library" alert — never a raw HTTP string.
 */
export const NotFound: Story = {
  parameters: { router: false },
  decorators: [stubFetch(() => httpError(404))],
  render: () => {
    return <ReaderAt />;
  },
};

/**
 * ERROR — the shell's OWN generic-failure state: an unknown error (the connection
 * dropped, the gate errored). The shell shows its calm §5 catch-all alert, never
 * the raw engine string. The endpoints answer 503.
 */
export const Error: Story = {
  parameters: { router: false },
  decorators: [stubFetch(() => httpError(503))],
  render: () => {
    return <ReaderAt />;
  },
};

/** Route every NON-book-detail/full-text call to a calm default so the resolved
 *  composition renders without its companion / talk / house secondary fetches
 *  erroring loudly. The book detail + full-text are supplied per story. */
function withBody(body: FullTextResponse, book: BookDetail = detail()) {
  return stubFetch((url) => {
    if (/\/full-text$/.test(url)) return json(body);
    if (/\/books\/[^/]+$/.test(url) && !/\/books\?/.test(url)) return json(book);
    if (/\/trajectory\//.test(url)) {
      return json({ investigation_id: `read-${DOC}`, count: 0, events: [] });
    }
    if (/\/books\?/.test(url)) return json({ books: [], count: 0 });
    return json({}, 404);
  });
}

/**
 * HOSTED BODY — the shell's resolved state: a servable book opens INTO the world.
 * The TOC, the paginated reading column, the per-page voice-note + research
 * actions, the attribution chrome, the pager, and the docked reading companion
 * all compose. The gate served full text, so the reader hosts the body.
 */
export const HostedBody: Story = {
  parameters: { router: false },
  decorators: [withBody(fullText())],
  render: () => {
    return <ReaderAt />;
  },
};

/**
 * PREVIEW ONLY (gated) — the shell's OWN gated-body notice: the book isn't
 * licensed for full reading, so the gate serves a bounded snippet and the shell
 * shows its "preview only" notice above the snippet (the §9.0 honest body cue),
 * with NO full text and NO ad rails attributed to withheld text.
 */
export const PreviewOnly: Story = {
  parameters: { router: false },
  decorators: [
    withBody(
      fullText({
        servable: false,
        servability: "gated_metadata_only",
        full_text: null,
        snippet: "A short licensed preview of the opening lines of the book…",
        ad_eligible: false,
      }),
      detail({ servability: "gated_metadata_only", servable_full_text: false }),
    ),
  ],
  render: () => {
    return <ReaderAt />;
  },
};

/**
 * REMOVED (taken down) — the shell's OWN taken-down notice: the title has been
 * removed and is no longer available to read. The gate serves no body and the
 * shell shows its honest "this title has been removed" notice — the §9.0
 * takedown state, authored, not a blank screen.
 */
export const Removed: Story = {
  parameters: { router: false },
  decorators: [
    withBody(
      fullText({
        servable: false,
        servability: "taken_down",
        full_text: null,
        snippet: null,
        ad_eligible: false,
      }),
      detail({ servability: "taken_down", servable_full_text: false, taken_down: true }),
    ),
  ],
  render: () => {
    return <ReaderAt />;
  },
};

/**
 * READ ON ARXIV (T2/T3 link-back) — the shell's OWN rights-tier branch: a gated
 * (T2) or rights-unknown (T3) arXiv paper is NOT hosted (body-serving is T1-only
 * by the rights law). The shell takes its link-back branch — the reliable
 * ArxivFrame card + the attribution chrome, with NO hosted body and NO ad rails.
 */
export const ReadOnArxiv: Story = {
  parameters: { router: false },
  decorators: [
    withBody(
      fullText({
        tier: "T2",
        canonical_url: "https://arxiv.org/abs/2401.12345",
        license: "https://creativecommons.org/licenses/by-nc/4.0/",
        ad_eligible: false,
        full_text: null,
        snippet: null,
      }),
      detail({ title: "Attention Is All You Need", author: "A. Vaswani et al." }),
    ),
  ],
  render: () => {
    return <ReaderAt />;
  },
};
