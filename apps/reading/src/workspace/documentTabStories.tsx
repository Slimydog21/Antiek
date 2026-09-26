/**
 * documentTabStories.tsx — fixture trees for the document-strip stories and
 * the story smoke test. Built through the real model (spawnChild), so a
 * story can never show a tree the model would refuse.
 */
import { useMemo, useState } from "react";

import { DocumentTabStripView, labelsFor, type StripStatus } from "./DocumentTabStrip";
import { titleKey, type TitleEntry } from "./tabTitles";
import { emptyTabTree, setActive, spawnChild, visitChild, type SpawnInput, type TabTree } from "./tabTree";

type Titles = Record<string, TitleEntry>;

const BOOKS = [
  "On the Origin of Species",
  "Principles of Geology",
  "The Voyage of the Beagle",
  "An Essay on the Principle of Population",
  "Zoonomia",
  "Philosophie zoologique",
  "Vestiges of the Natural History of Creation",
  "The Descent of Man",
];

const PASSAGES = [
  "ch. 3, the struggle for existence",
  "n. 12, on Malthus",
  "Lyell on the uniformity of causes",
  "fig. 4, the tree of life",
  "the Galápagos finches",
  "a citation to Hooker, 1847",
];

export interface Fixture {
  tree: TabTree;
  titles: Titles;
}

function builder() {
  let tree = emptyTabTree("reading");
  const titles: Titles = {};
  let n = 0;
  function add(parent: string | null, input: Omit<SpawnInput, "tab_id" | "mothership">, title?: string | null): string {
    const id = `t${n++}`;
    const r = spawnChild(tree, parent, { ...input, tab_id: id, mothership: "reading", activate: false });
    if (!r.ok) throw new Error(r.error.message);
    tree = r.tree;
    if (title !== undefined) titles[titleKey(input.kind, input.ref)] = { state: "known", title };
    return id;
  }
  return {
    add,
    activate(id: string) {
      const r = setActive(tree, id);
      if (!r.ok) throw new Error(r.error.message);
      tree = r.tree;
    },
    done: (): Fixture => ({ tree, titles }),
  };
}

/**
 * A reading forest whose active tab sits at `depth`: three root books, a
 * rabbit hole of alternating references (a new book, named by title) and
 * footnotes (the same book, named by passage) down to `depth`, with two
 * siblings at every level so the strip always has neighbours.
 */
export function depthFixture(depth: number): Fixture {
  const b = builder();
  const roots = [0, 1, 2].map((i) => b.add(null, { kind: "reader", ref: `book-${i}` }, BOOKS[i]));
  let parent = roots[0];
  let parentRef = "book-0";
  for (let level = 2; level <= depth; level++) {
    const reference = level % 2 === 0;
    const ref = reference ? `book-${3 + (level % 5)}-${level}` : parentRef;
    const passage = PASSAGES[level % PASSAGES.length];
    const origin = { document_id: parentRef, kind: reference ? ("reference" as const) : ("footnote" as const), anchor: { document_id: parentRef, quote: passage } };
    const id = b.add(parent, { kind: "reader", ref, origin }, reference ? BOOKS[3 + (level % 5)] : undefined);
    // A sibling on every level: a research branch, its question unknown yet.
    b.add(parent, { kind: "research", ref: `/inv/branch-${level}`, origin: { document_id: parentRef, kind: "research" } });
    parent = id;
    parentRef = ref;
  }
  // The active tab has children too, so the ↳n chip shows.
  b.add(parent, { kind: "reader", ref: parentRef, origin: { document_id: parentRef, kind: "footnote", anchor: { document_id: parentRef, quote: "n. 3" } } });
  b.add(parent, { kind: "document", ref: "/write/notes" }, "Notes toward chapter 2");
  b.activate(parent);
  return b.done();
}

/** One parent with `count` children: the operator's 174-tab workspace. */
export function siblingsFixture(count: number): Fixture {
  const b = builder();
  const root = b.add(null, { kind: "reader", ref: "book-0" }, BOOKS[0]);
  let pick = root;
  for (let i = 0; i < count; i++) {
    const kind = i % 7 === 3 ? "research" : "reader";
    const ref = kind === "research" ? `/inv/q-${i}` : `cite-${i}`;
    const title = kind === "research" ? `Did ${BOOKS[i % BOOKS.length]} anticipate selection?` : `${BOOKS[i % BOOKS.length]} (${1790 + i})`;
    const id = b.add(root, { kind, ref, origin: { document_id: "book-0", kind: "citation" } }, title);
    if (i === 87) pick = id;
  }
  b.activate(pick);
  return b.done();
}

/** A tree with no tabs (the empty panel). */
export function emptyFixture(): Fixture {
  return { tree: emptyTabTree("research"), titles: {} };
}

/** An interactive strip over a fixture: clicks, the chip and the panel work. */
export function StoryStrip({
  fixture,
  status = "ready",
  panelOpen = false,
}: {
  fixture: Fixture;
  status?: StripStatus;
  panelOpen?: boolean;
}) {
  const [tree, setTree] = useState(fixture.tree);
  const [open, setOpen] = useState(panelOpen);
  const [focus, setFocus] = useState<string | null>(null);
  const labelOf = useMemo(() => labelsFor(tree, fixture.titles), [tree, fixture.titles]);
  return (
    <div className="min-h-[520px] p-4" style={{ background: "var(--bg-page)" }}>
      <div className="flex h-[480px] max-w-[760px] flex-col overflow-visible rounded-lg border border-hairline bg-ice-0 dark:bg-charcoal-2">
        <DocumentTabStripView
          status={status}
          errorDetail={status === "error" ? "GET /projects/default/tabs/reading: HTTP 503" : null}
          onRetry={() => {}}
          tree={status === "ready" ? tree : null}
          labelOf={labelOf}
          treePanelOpen={open}
          subtreeFocusId={focus}
          onActivate={(id) => {
            const r = setActive(tree, id);
            if (r.ok) setTree(r.tree);
          }}
          onToggleTree={() => setOpen((o) => !o)}
          onFocusSubtree={setFocus}
          onVisitChild={() => {
            if (!tree.active_tab_id) return;
            const r = visitChild(tree, tree.active_tab_id);
            if (r.ok) setTree(r.tree);
          }}
        />
        <div className="flex-1 overflow-hidden p-6 font-serif text-base leading-7 text-ink dark:text-bright">
          <p className="max-w-[62ch]">
            When on board H.M.S. Beagle, as naturalist, I was much struck with certain facts in the
            distribution of the inhabitants of South America, and in the geological relations of the
            present to the past inhabitants of that continent.
          </p>
        </div>
      </div>
    </div>
  );
}
