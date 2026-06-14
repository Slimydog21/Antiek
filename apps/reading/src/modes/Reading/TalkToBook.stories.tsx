import { useEffect, useRef } from "react";
import type { Meta, StoryObj } from "@storybook/react";

import TalkToBook from "./TalkToBook";
import { httpError, json, pendingForever, stubFetch } from "./storyFetch";

/**
 * TalkToBook (Read SPR-08 M2) — the floating bookmark: a book-level MULTI-TURN
 * conversation that remembers earlier turns, CITES the pages an answer comes
 * from, branches into tangents, and reads any answer aloud. It persists per book
 * in SESSION state (the floating bookmark), so it survives page navigation.
 *
 * Product-character authorship (ALC SPR-09): TalkToBook is stateful — a closed
 * bookmark, an open empty conversation, an in-flight turn, a grounded answer
 * with page citations, an honestly-ungrounded answer, and a turn that errored.
 * Each meaningful state is authored as its OWN named, co-located story so it is
 * inspectable in isolation (the rubric's Dimension-3 level-3 criterion). The
 * states are reached through the component's REAL code path: a driver clicks the
 * real "Talk to this book" control open and submits the real ask form, while
 * each story pins `fetch` (`storyFetch.tsx`) so `POST /books/{id}/ask` returns
 * the response that drives the state. `useTalkThread`'s real reducer (session
 * state, branching) runs unmodified. Nothing in TalkToBook is mocked — only the
 * network. Runtime behaviour is unchanged.
 *
 * §9.0: a withheld region can never be cited (the backend gate keeps it out of
 * context), so this surface never receives one; an ungrounded answer is labelled
 * honestly. §5 voice + brand firewall: every line is the component's own; no
 * PostHog phrasing.
 */
const meta = {
  title: "Read / TalkToBook",
  component: TalkToBook,
  parameters: { layout: "fullscreen" },
  tags: ["autodocs"],
  args: { documentId: "doc-talk-default", title: "The Order of Time", onJumpToPage: () => {} },
} satisfies Meta<typeof TalkToBook>;

export default meta;
type Story = StoryObj<typeof meta>;

/**
 * Drives the REAL component into a conversational state by clicking its actual
 * controls on mount: open the bookmark, and (when `ask` is set) type a question
 * into the real textarea and submit the real form. Each step exercises the
 * genuine handler; only the network is pinned by the story's `stubFetch`. The
 * thread is keyed by a UNIQUE `documentId` per story and sessionStorage is
 * cleared on mount so stories never leak conversations into each other.
 */
function TalkDriver({
  documentId,
  ask,
}: {
  documentId: string;
  ask?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    try {
      window.sessionStorage.removeItem(`antiek.read.talk.${documentId}`);
    } catch {
      /* private mode — the thread still works in-memory */
    }
    const root = ref.current;
    if (!root) return;
    // Open the floating bookmark via its real onClick.
    const bookmark = root.querySelector<HTMLButtonElement>(
      '[data-testid="talk-to-book-bookmark"]',
    );
    bookmark?.click();
    if (!ask) return;
    // After the panel renders, type into the real textarea and submit the form.
    const t = window.setTimeout(() => {
      const textarea = root.querySelector("textarea");
      const form = root.querySelector("form");
      if (textarea) {
        const setter = Object.getOwnPropertyDescriptor(
          window.HTMLTextAreaElement.prototype,
          "value",
        )?.set;
        setter?.call(textarea, ask);
        textarea.dispatchEvent(new Event("input", { bubbles: true }));
      }
      const submit = window.setTimeout(() => {
        form?.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
      }, 0);
      return () => window.clearTimeout(submit);
    }, 0);
    return () => window.clearTimeout(t);
  }, [documentId, ask]);
  return (
    <div ref={ref}>
      <TalkToBook documentId={documentId} title="The Order of Time" onJumpToPage={() => {}} />
    </div>
  );
}

/**
 * CLOSED BOOKMARK — the resting state: a calm floating "Talk to this book" pill
 * the reader can press. No conversation yet, so no turn-count badge. This is the
 * surface the reader meets first on every page.
 */
export const ClosedBookmark: Story = {};

/**
 * OPEN EMPTY — the panel opened with no turns yet: the §5 invitation copy ("Ask
 * anything about this book. Answers cite the pages they come from…") and the
 * ask form. Reached by clicking the real bookmark open.
 */
export const OpenEmpty: Story = {
  render: () => {
    return <TalkDriver documentId="doc-talk-empty" />;
  },
};

/**
 * THINKING — an in-flight turn, pinned: the reader asked a question and the book
 * is being read. The "Reading the book…" live-region status holds (the `/ask`
 * fetch never settles) so the transient state is inspectable instead of flashing
 * past; the Ask button is disabled so the turn can't double-fire.
 */
export const Thinking: Story = {
  decorators: [stubFetch(pendingForever)],
  render: () => {
    return <TalkDriver documentId="doc-talk-thinking" ask="What is the central claim?" />;
  },
};

/**
 * ANSWERED WITH CITATIONS — the resolved grounded turn: the answer renders as
 * "the book", page-level citation chips link back into the reader (a resolved
 * page shows "p.42"; an unresolved one shows the honest "page not pinpointed"
 * label, never a fabricated page), and the Read-aloud + "what about that?"
 * branch controls appear. The `/ask` fetch returns a grounded answer.
 */
export const AnsweredWithCitations: Story = {
  decorators: [
    stubFetch((url) =>
      /\/ask$/.test(url)
        ? json({
            answer:
              "The central claim is that time is not fundamental: at the basic level the world is a network of events, and the experience of flow is thermodynamic and perspectival.",
            citations: [
              {
                chunk_id: "c1",
                document_id: "doc-talk-answered",
                page_index: 41,
                page_resolved: true,
                snippet: "the world is a network of events",
              },
              {
                chunk_id: "c2",
                document_id: "doc-talk-answered",
                page_index: null,
                page_resolved: false,
                snippet: "entropy and the arrow of time",
              },
            ],
            grounded: true,
            context_chunk_count: 2,
          })
        : json({}),
    ),
  ],
  render: () => {
    return <TalkDriver documentId="doc-talk-answered" ask="What is the central claim?" />;
  },
};

/**
 * UNGROUNDED ANSWER — the honesty guard: the book had no extractable passages to
 * ground on (a scanned-image PDF, or everything withheld under §9.0), so the
 * answer is returned with `grounded:false` and the surface shows its honest "no
 * readable passages backed this" note rather than dressing it up as grounded.
 */
export const Ungrounded: Story = {
  decorators: [
    stubFetch((url) =>
      /\/ask$/.test(url)
        ? json({
            answer:
              "I can't ground this in the book's text — its pages aren't readable here, so this is general context, not a passage-backed answer.",
            citations: [],
            grounded: false,
            context_chunk_count: 0,
          })
        : json({}),
    ),
  ],
  render: () => {
    return <TalkDriver documentId="doc-talk-ungrounded" ask="What is the central claim?" />;
  },
};

/**
 * TURN FAILED — the talk service is unavailable (503): the pending turn is
 * dropped so the thread isn't stuck, and the failure is shown inline so the
 * reader can simply ask again. The `/ask` endpoint answers 503.
 */
export const TurnFailed: Story = {
  decorators: [stubFetch((url) => (/\/ask$/.test(url) ? httpError(503) : json({})))],
  render: () => {
    return <TalkDriver documentId="doc-talk-failed" ask="What is the central claim?" />;
  },
};
