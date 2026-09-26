/**
 * Property proof for the branch tab tree (MS-04 milestone 1).
 *
 * INVARIANTS, written before the model (rigor card #3). `checkInvariants`
 * encodes the single-state ones; `stepViolations` below adds the ones that
 * compare two states.
 *
 *  (I1) Every hier_number is unique across open + history.
 *  (I2) Every non-null public_number is unique across open + history.
 *  (I3) Stability: once assigned, a tab's hier_number never changes, and a
 *       non-null public_number never changes. The one exception is a PENDING
 *       spawn that rebase recomputes, because a number is final only once
 *       the snapshot carrying it is accepted (contract R3-5).
 *  (I4) No number is reused under the same parent: every per-parent counter
 *       (root included) is monotonic and stays above every index already
 *       issued under that parent, open or closed.
 *  (I5) Parent/child consistency: child_order <=> parent_tab_id, root_order
 *       <=> roots, no cycles, no dangling ids (last_visited_child_id is one
 *       of the node's own children), open and history are disjoint.
 *  (I6) prune + undo and lift + undo restore a deep-equal tree (toStrictEqual,
 *       version included) when nothing happened in between. Numbers come
 *       back to the SAME tab_ids, which is not reuse (R3-1): reuse is a
 *       DIFFERENT tab_id taking a number, checked by `numberReuse`.
 *  (I7) lift_children keeps the lifted children's numbers: they move to the
 *       closed tab's parent, at its position, with the hier_numbers they had.
 *  (I8) active_tab_id is null or an open tab.
 *  (I9) Added while designing: every open tab's parent has a hier_number that
 *       is a proper dotted prefix of the tab's own. The parent is always a
 *       spawn-ancestor, which is why lift can keep numbers and why no
 *       sequence of lift/undo/re-home can build a cycle.
 *
 * ENCODED TWO WAYS
 *  (a) Exhaustive: every sequence of length 1..6 over {spawn, prune, lift,
 *      undo}: 4 + 16 + 64 + 256 + 1024 + 4096 = 5,460 sequences, each
 *      replayed from an empty tree with every check after every step. The
 *      targets are deterministic, and there are three targeting policies,
 *      because with only "the newest open tab" every close hits a leaf and
 *      lift would never have children to lift. That makes 3 x 5,460 = 16,380
 *      sequences.
 *  (b) Seeded random (mulberry32 from src/scene/rng.ts): SEED below; each
 *      sequence i runs on seed SEED + i, so any failure replays on its own
 *      and is shrunk (greedy one-op deletion) before it is reported.
 *      - 1,000 single-device sequences, length 1..60, with random targets
 *        and non-LIFO undo;
 *      - 1,000 two-device runs: a shared base, each device mutates its own
 *        copy independently, the remote wins the PUT, and the local device
 *        rebases through the in-memory adapter and must be accepted;
 *      - 40 deep sequences of length 320, biased to chain, to reach depth
 *        >= 200.
 */

import { describe, expect, it } from "vitest";

import { makeRng, type Rng } from "../scene/rng";
import {
  checkInvariants,
  closeTab,
  createInMemoryTabTreeAdapter,
  emptyTabTree,
  fromSnapshot,
  numberReuse,
  rebase,
  setActive,
  spawnChild,
  assignPublicNumber,
  toSnapshot,
  undo,
  visitChild,
  depthOf,
  type CloseMode,
  type TabOp,
  type TabTree,
  type UndoToken,
} from "./tabTree";

// ---------------------------------------------------------------------------
// Recorded bounds (rigor card: "record the seed and the sequence-length bound")
// ---------------------------------------------------------------------------
export const SEED = 0x04a7ab1e;
const EXHAUSTIVE_MAX_LENGTH = 6;
const RANDOM_SEQUENCES = 1_000;
const RANDOM_MAX_LENGTH = 60;
const TWO_DEVICE_RUNS = 1_000;
const TWO_DEVICE_MAX_LENGTH = 30;
const DEEP_SEQUENCES = 20;
const DEEP_LENGTH = 300;
const DEEP_CHAIN_BIAS = 0.9;
const DEEP_TARGET_DEPTH = 200;

const MOTHERSHIP = "research" as const;

// ---------------------------------------------------------------------------
// Shared checks
// ---------------------------------------------------------------------------

/** Freeze a whole tree, so any mutation of an op's input throws (ES modules
 *  are strict). Recursion here follows object nesting (tree -> nodes -> node
 *  -> child_order), never tab depth. */
function deepFreeze<T>(value: T): T {
  if (value !== null && typeof value === "object" && !Object.isFrozen(value)) {
    Object.freeze(value);
    for (const key of Object.keys(value)) {
      deepFreeze((value as Record<string, unknown>)[key]);
    }
  }
  return value;
}

/** Strict structural equality for JSON-shaped data, used in the bulk loops
 *  because toStrictEqual costs ~4 ms on a 480-node tree. Same rules as
 *  toStrictEqual for this data: same own keys (a key holding undefined is NOT
 *  a missing key), same prototype, same array lengths, primitives by ===.
 *  Its agreement with toStrictEqual is tested below. Recursion follows object
 *  nesting (at most 5 levels), never tab depth. */
function strictSame(a: unknown, b: unknown): boolean {
  if (a === b) return true;
  if (typeof a !== "object" || typeof b !== "object" || a === null || b === null) return false;
  if (Object.getPrototypeOf(a) !== Object.getPrototypeOf(b)) return false;
  const ka = Object.keys(a);
  if (ka.length !== Object.keys(b).length) return false;
  for (const k of ka) {
    if (!Object.hasOwn(b, k)) return false;
    if (!strictSame((a as Record<string, unknown>)[k], (b as Record<string, unknown>)[k])) return false;
  }
  return true;
}

type Held = Map<string, { hier: string; pub: number | null; open: boolean }>;

function held(tree: TabTree): Held {
  const out: Held = new Map();
  for (const id of Object.keys(tree.nodes)) {
    const n = tree.nodes[id];
    out.set(id, { hier: n.hier_number, pub: n.public_number, open: true });
  }
  for (const id of Object.keys(tree.history)) {
    const n = tree.history[id].node;
    out.set(id, { hier: n.hier_number, pub: n.public_number, open: false });
  }
  return out;
}

/** I3 across one step: no tab vanishes, no hier_number changes, and a public
 *  number, once set, never changes. `except` holds the pending spawns a rebase
 *  may renumber. */
function stabilityViolations(
  before: TabTree,
  after: TabTree,
  except: ReadonlySet<string> = new Set(),
): string[] {
  const out: string[] = [];
  const a = held(after);
  for (const [id, b] of held(before)) {
    if (except.has(id)) continue;
    const now = a.get(id);
    if (!now) {
      out.push(`I3: tab ${id} vanished`);
      continue;
    }
    if (now.hier !== b.hier) out.push(`I3: ${id} hier ${b.hier} -> ${now.hier}`);
    if (b.pub !== null && now.pub !== b.pub) out.push(`I3: ${id} public ${b.pub} -> ${now.pub}`);
  }
  return out;
}

/** I4 across one step: no counter goes down. */
function counterViolations(before: TabTree, after: TabTree): string[] {
  const out: string[] = [];
  if (after.next_root_index < before.next_root_index) {
    out.push(`I4: root counter ${before.next_root_index} -> ${after.next_root_index}`);
  }
  for (const id of Object.keys(before.next_child_index)) {
    const b = before.next_child_index[id];
    const a = Object.hasOwn(after.next_child_index, id) ? after.next_child_index[id] : 0;
    if (a < b) out.push(`I4: counter of ${id} ${b} -> ${a}`);
  }
  return out;
}

function roundTrip(tree: TabTree): string[] {
  const wire = JSON.parse(JSON.stringify(toSnapshot(tree)));
  if (JSON.stringify(wire).includes('"island"')) return ["snapshot: 'island' reached the wire"];
  const back = fromSnapshot(wire);
  if (!back.ok) return [`snapshot: fromSnapshot refused its own output: ${back.error.message}`];
  return strictSame(back.tree, tree) ? [] : ["snapshot: round trip is not deep-equal"];
}

/** The documented active-tab rule after a close (see closeTab). */
function expectedActiveAfterClose(before: TabTree, after: TabTree, tabId: string, removed: Set<string>): string | null {
  if (before.active_tab_id === null || !removed.has(before.active_tab_id)) return before.active_tab_id;
  const parent = before.nodes[tabId].parent_tab_id;
  if (parent !== null) return parent;
  const index = before.root_order.indexOf(tabId);
  if (index > 0) return after.root_order[index - 1];
  return after.root_order[index] ?? null;
}

function subtreeOf(tree: TabTree, id: string): string[] {
  const out: string[] = [];
  const stack = [id];
  while (stack.length > 0) {
    const cur = stack.pop() as string;
    out.push(cur);
    stack.push(...tree.nodes[cur].child_order);
  }
  return out;
}

/** I6 and I7 plus the active rule, for one close. */
function closeViolations(before: TabTree, after: TabTree, tabId: string, mode: CloseMode, token: UndoToken, now: string): string[] {
  const out: string[] = [];
  const x = before.nodes[tabId];
  const removed = new Set(mode === "prune" ? subtreeOf(before, tabId) : [tabId]);
  for (const id of removed) {
    const h = Object.hasOwn(after.history, id) ? after.history[id] : undefined;
    if (!h || h.node.pruned_at !== now) out.push(`close: ${id} not in history with pruned_at`);
    if (Object.hasOwn(after.nodes, id)) out.push(`close: ${id} still open`);
  }
  if (mode === "lift_children") {
    // I7: children keep their numbers and take the closed tab's place.
    const siblings = x.parent_tab_id === null ? after.root_order : after.nodes[x.parent_tab_id].child_order;
    const beforeSiblings = x.parent_tab_id === null ? before.root_order : before.nodes[x.parent_tab_id].child_order;
    const at = beforeSiblings.indexOf(tabId);
    const expected = [...beforeSiblings.slice(0, at), ...x.child_order, ...beforeSiblings.slice(at + 1)];
    if (JSON.stringify(siblings) !== JSON.stringify(expected)) out.push("I7: lifted children not at the closed tab's position");
    for (const c of x.child_order) {
      const n = after.nodes[c];
      if (!n) out.push(`I7: lifted child ${c} not open`);
      else {
        if (n.hier_number !== before.nodes[c].hier_number) out.push(`I7: lifted child ${c} renumbered`);
        if (n.parent_tab_id !== x.parent_tab_id) out.push(`I7: lifted child ${c} has the wrong parent`);
      }
    }
  }
  const want = expectedActiveAfterClose(before, after, tabId, removed);
  if (after.active_tab_id !== want) out.push(`active: expected ${want}, got ${after.active_tab_id}`);
  // I6: an immediate undo restores the tree exactly.
  const back = undo(after, token);
  if (!back.ok) out.push(`I6: immediate undo refused: ${back.error.message}`);
  else {
    if (!strictSame(back.tree, before)) out.push(`I6: ${mode} + undo is not deep-equal`);
    if (numberReuse(before, back.tree).length > 0) out.push("I6: undo reused a number");
  }
  return out;
}

function stepViolations(before: TabTree, after: TabTree): string[] {
  return [
    ...checkInvariants(after),
    ...stabilityViolations(before, after),
    ...counterViolations(before, after),
    ...numberReuse(before, after).map((v) => `R3-1: ${v}`),
    ...roundTrip(after),
  ];
}

// ---------------------------------------------------------------------------
// (a) Exhaustive enumeration
// ---------------------------------------------------------------------------

type EnumOp = "spawn" | "prune" | "lift" | "undo";
const ENUM_OPS: readonly EnumOp[] = ["spawn", "prune", "lift", "undo"];

interface Policy {
  name: string;
  /** Spawn under the active tab; activate the child? */
  activateOnSpawn: boolean;
  /** Close the newest open tab, or prefer the newest one with children. */
  preferParent: boolean;
}

const POLICIES: readonly Policy[] = [
  { name: "chain: newest open tab", activateOnSpawn: true, preferParent: false },
  { name: "interior: newest open tab with children", activateOnSpawn: true, preferParent: true },
  { name: "fan: background spawns, newest with children", activateOnSpawn: false, preferParent: true },
];

interface EnumWorld {
  tree: TabTree;
  tokens: UndoToken[];
  spawned: string[];
  step: number;
}

function closeTarget(w: EnumWorld, preferParent: boolean): string | null {
  let newest: string | null = null;
  for (let i = w.spawned.length - 1; i >= 0; i--) {
    const id = w.spawned[i];
    if (!Object.hasOwn(w.tree.nodes, id)) continue;
    if (newest === null) newest = id;
    if (!preferParent || w.tree.nodes[id].child_order.length > 0) return id;
  }
  return newest;
}

function runEnumStep(w: EnumWorld, op: EnumOp, policy: Policy): { world: EnumWorld; violations: string[] } {
  const before = deepFreeze(w.tree);
  const step = w.step + 1;
  const now = `2026-09-24T00:00:00.${String(step).padStart(3, "0")}Z`;
  if (op === "spawn") {
    const id = `t${w.spawned.length + 1}`;
    const activate = policy.activateOnSpawn || before.active_tab_id === null;
    const r = spawnChild(before, before.active_tab_id, { tab_id: id, kind: "reader", ref: `doc-${id}`, mothership: MOTHERSHIP, activate });
    if (!r.ok) return { world: w, violations: [`spawn refused: ${r.error.message}`] };
    return { world: { ...w, tree: r.tree, spawned: [...w.spawned, id], step }, violations: stepViolations(before, r.tree) };
  }
  if (op === "prune" || op === "lift") {
    const target = closeTarget(w, policy.preferParent);
    if (target === null) return { world: { ...w, step }, violations: [] };
    const mode: CloseMode = op === "prune" ? "prune" : "lift_children";
    const r = closeTab(before, target, mode, now);
    if (!r.ok) return { world: w, violations: [`close refused: ${r.error.message}`] };
    return {
      world: { ...w, tree: r.tree, tokens: [...w.tokens, r.undo], step },
      violations: [...stepViolations(before, r.tree), ...closeViolations(before, r.tree, target, mode, r.undo, now)],
    };
  }
  const token = w.tokens[w.tokens.length - 1];
  if (token === undefined) return { world: { ...w, step }, violations: [] };
  const r = undo(before, token);
  if (!r.ok) return { world: w, violations: [`undo refused: ${r.error.message}`] };
  return { world: { ...w, tree: r.tree, tokens: w.tokens.slice(0, -1), step }, violations: stepViolations(before, r.tree) };
}

describe("tab tree: exhaustive enumeration (I1-I9 after every step)", () => {
  for (const policy of POLICIES) {
    it(`every sequence of length <= ${EXHAUSTIVE_MAX_LENGTH} holds every invariant (${policy.name})`, () => {
      let sequences = 0;
      let steps = 0;
      let lifts = 0;
      let liftsWithChildren = 0;
      let maxDepth = 0;
      const failures: string[] = [];
      for (let length = 1; length <= EXHAUSTIVE_MAX_LENGTH; length++) {
        const total = 4 ** length;
        for (let code = 0; code < total; code++) {
          const seq: EnumOp[] = [];
          let c = code;
          for (let i = 0; i < length; i++) {
            seq.push(ENUM_OPS[c % 4]);
            c = Math.floor(c / 4);
          }
          let w: EnumWorld = { tree: emptyTabTree(MOTHERSHIP), tokens: [], spawned: [], step: 0 };
          for (const op of seq) {
            if (op === "lift") {
              lifts++;
              const t = closeTarget(w, policy.preferParent);
              if (t !== null && w.tree.nodes[t].child_order.length > 0) liftsWithChildren++;
            }
            const r = runEnumStep(w, op, policy);
            steps++;
            if (r.violations.length > 0 && failures.length < 5) failures.push(`[${seq.join(",")}] ${r.violations.join("; ")}`);
            w = r.world;
            for (const id of Object.keys(w.tree.nodes)) maxDepth = Math.max(maxDepth, depthOf(w.tree, id));
          }
          sequences++;
        }
      }
      console.info(
        `[tabTree exhaustive] ${policy.name}: sequences=${sequences} steps=${steps} lifts=${lifts} liftsWithChildren=${liftsWithChildren} maxDepth=${maxDepth}`,
      );
      expect(failures).toEqual([]);
      expect(sequences).toBe(5_460);
      // Guard against a vacuous enumeration: under the interior policies lift
      // must really lift children. (Under "newest open tab" every close hits
      // a leaf, which is why the other two policies exist.)
      if (policy.preferParent) expect(liftsWithChildren).toBeGreaterThan(0);
    }, 60_000);
  }
});

// ---------------------------------------------------------------------------
// (b) Seeded random sequences
// ---------------------------------------------------------------------------

type ChoiceKind = "spawn" | "prune" | "lift" | "undo" | "assign" | "collide" | "active" | "visit" | "stale_undo";
interface Choice {
  kind: ChoiceKind;
  a: number;
  b: number;
  c: number;
}

const WEIGHTS: ReadonlyArray<[ChoiceKind, number]> = [
  ["spawn", 34],
  ["prune", 10],
  ["lift", 10],
  ["undo", 10],
  ["assign", 12],
  ["collide", 6],
  ["active", 8],
  ["visit", 6],
  ["stale_undo", 4],
];

/** Deep runs keep every op but prune less, so one random prune does not
 *  keep collapsing the chain they are building. */
const DEEP_WEIGHTS: ReadonlyArray<[ChoiceKind, number]> = WEIGHTS.map(([k, w]) => [k, k === "prune" ? 2 : w]);

function drawChoice(rng: Rng, chainBias = 0): Choice {
  if (chainBias > 0 && rng.next() < chainBias) return { kind: "spawn", a: -1, b: rng.next(), c: rng.next() };
  const weights = chainBias > 0 ? DEEP_WEIGHTS : WEIGHTS;
  const total = weights.reduce((s, [, w]) => s + w, 0);
  let x = rng.next() * total;
  let kind: ChoiceKind = "spawn";
  for (const [k, w] of weights) {
    if (x < w) {
      kind = k;
      break;
    }
    x -= w;
  }
  return { kind, a: rng.next(), b: rng.next(), c: rng.next() };
}

function drawSequence(seed: number, maxLength: number, chainBias = 0, exactLength = false): Choice[] {
  const rng = makeRng(seed);
  const length = exactLength ? maxLength : rng.int(1, maxLength);
  const out: Choice[] = [];
  for (let i = 0; i < length; i++) out.push(drawChoice(rng, chainBias));
  return out;
}

/** Where public numbers come from: a counter for one device, or a pool the
 *  in-memory server allocated for two. The model never invents one. */
interface Allocator {
  take(): number;
}

function counterAllocator(): Allocator {
  let n = 1;
  return { take: () => n++ };
}

interface Device {
  tree: TabTree;
  prefix: string;
  spawned: string[];
  live: UndoToken[];
  used: UndoToken[];
  pending: TabOp[];
  step: number;
  /** The tab chain spawns extend (deep runs). */
  tip: string | null;
}

function pick<T>(items: readonly T[], r: number): T | undefined {
  if (items.length === 0) return undefined;
  return items[Math.min(items.length - 1, Math.floor(r * items.length))];
}

function openIds(d: Device): string[] {
  return d.spawned.filter((id) => Object.hasOwn(d.tree.nodes, id)).concat(
    Object.keys(d.tree.nodes).filter((id) => !d.spawned.includes(id)).sort(),
  );
}

function knownIds(d: Device): string[] {
  return [...Object.keys(d.tree.nodes), ...Object.keys(d.tree.history)].sort();
}

/** Apply one random choice to a device, checking every property. */
function applyChoice(d: Device, ch: Choice, alloc: Allocator): { device: Device; violations: string[] } {
  const before = deepFreeze(d.tree);
  const step = d.step + 1;
  const now = `2026-09-24T01:00:00.${String(step).padStart(4, "0")}Z`;
  const opens = openIds(d);
  const done = (tree: TabTree, extra: Partial<Device>, op: TabOp | null, more: string[] = []) => ({
    device: { ...d, ...extra, tree, step, pending: op ? [...d.pending, op] : d.pending },
    violations: [...stepViolations(before, tree), ...more],
  });
  switch (ch.kind) {
    case "spawn": {
      const id = `${d.prefix}${d.spawned.length + 1}`;
      // a = -1 means "chain": extend the chain tip (else the newest open tab).
      let parent: string | null;
      if (ch.a < 0) {
        parent =
          d.tip !== null && Object.hasOwn(before.nodes, d.tip)
            ? d.tip
            : ([...d.spawned].reverse().find((s) => Object.hasOwn(before.nodes, s)) ?? null);
      } else parent = ch.a < 0.15 ? null : (pick(opens, ch.a) ?? null);
      const kinds = ["footnote", "reference", "citation", "island", "research", "manual"] as const;
      const origin = parent === null ? undefined : { document_id: `doc-${parent}`, kind: kinds[Math.floor(ch.c * 6)] };
      const r = spawnChild(before, parent, {
        tab_id: id,
        kind: "reader",
        ref: `doc-${id}`,
        mothership: MOTHERSHIP,
        activate: ch.b < 0.7,
        ...(origin ? { origin } : {}),
      });
      if (!r.ok) return { device: d, violations: [`spawn refused: ${r.error.message}`] };
      return done(r.tree, { spawned: [...d.spawned, id], tip: ch.a < 0 ? id : d.tip }, r.op);
    }
    case "prune":
    case "lift": {
      const target = pick(opens, ch.a);
      if (target === undefined) return { device: { ...d, step }, violations: [] };
      const mode: CloseMode = ch.kind === "prune" ? "prune" : "lift_children";
      const r = closeTab(before, target, mode, now, `${d.prefix}close${step}`);
      if (!r.ok) return { device: d, violations: [`close refused: ${r.error.message}`] };
      return done(r.tree, { live: [...d.live, r.undo] }, r.op, closeViolations(before, r.tree, target, mode, r.undo, now));
    }
    case "undo": {
      // Non-LIFO: any live token, not only the newest.
      const token = pick(d.live, ch.a);
      if (token === undefined) return { device: { ...d, step }, violations: [] };
      const r = undo(before, token);
      if (!r.ok) return { device: d, violations: [`undo refused a live token: ${r.error.message}`] };
      const extra: string[] = [];
      for (const id of [token.tab_id]) if (!Object.hasOwn(r.tree.nodes, id)) extra.push(`undo: ${id} not reopened`);
      return done(r.tree, { live: d.live.filter((t) => t !== token), used: [...d.used, token] }, r.op, extra);
    }
    case "stale_undo": {
      const token = pick(d.used, ch.a);
      if (token === undefined) return { device: { ...d, step }, violations: [] };
      const r = undo(before, token);
      const out: string[] = [];
      if (r.ok) out.push("stale undo token was accepted");
      return { device: { ...d, step }, violations: out };
    }
    case "assign": {
      // Only the device that spawned a tab allocates its number.
      const candidates = knownIds(d).filter((id) => {
        const n = Object.hasOwn(before.nodes, id) ? before.nodes[id] : before.history[id].node;
        return id.startsWith(d.prefix) && n.public_number === null;
      });
      const target = pick(candidates, ch.a);
      if (target === undefined) return { device: { ...d, step }, violations: [] };
      const n = alloc.take();
      const r = assignPublicNumber(before, target, n);
      if (!r.ok) return { device: d, violations: [`assign of a fresh number refused: ${r.error.message}`] };
      return done(r.tree, {}, r.op);
    }
    case "collide": {
      // Try to give tab X a number another tab already holds (open OR history).
      const holders = knownIds(d).filter((id) => {
        const n = Object.hasOwn(before.nodes, id) ? before.nodes[id] : before.history[id].node;
        return n.public_number !== null;
      });
      const holder = pick(holders, ch.a);
      const target = pick(knownIds(d).filter((id) => id !== holder), ch.b);
      if (holder === undefined || target === undefined) return { device: { ...d, step }, violations: [] };
      const taken = (Object.hasOwn(before.nodes, holder) ? before.nodes[holder] : before.history[holder].node).public_number as number;
      const r = assignPublicNumber(before, target, taken);
      return { device: { ...d, step }, violations: r.ok ? [`assignPublicNumber gave ${target} the number ${taken} held by ${holder}`] : [] };
    }
    case "active": {
      const target = ch.a < 0.1 ? null : (pick(opens, ch.a) ?? null);
      const r = setActive(before, target);
      if (!r.ok) return { device: d, violations: [`setActive refused: ${r.error.message}`] };
      const extra: string[] = [];
      // last_visited_child_id is maintained along the whole path.
      let child = target;
      while (child !== null) {
        const p = r.tree.nodes[child].parent_tab_id;
        if (p !== null && r.tree.nodes[p].last_visited_child_id !== child) extra.push(`visit: ${p} does not remember ${child}`);
        child = p;
      }
      return done(r.tree, {}, r.op, extra);
    }
    case "visit": {
      const target = pick(opens.filter((id) => before.nodes[id].child_order.length > 0), ch.a);
      if (target === undefined) return { device: { ...d, step }, violations: [] };
      const r = visitChild(before, target);
      if (!r.ok) return { device: d, violations: [`visitChild refused: ${r.error.message}`] };
      return done(r.tree, {}, r.op);
    }
  }
}

function newDevice(tree: TabTree, prefix: string): Device {
  return { tree, prefix, spawned: [], live: [], used: [], pending: [], step: 0, tip: null };
}

function runSingle(seq: readonly Choice[]): { violations: string[]; maxDepth: number } {
  let d = newDevice(emptyTabTree(MOTHERSHIP), "t");
  const alloc = counterAllocator();
  let maxDepth = 0;
  for (const ch of seq) {
    const r = applyChoice(d, ch, alloc);
    if (r.violations.length > 0) return { violations: r.violations, maxDepth };
    d = r.device;
    const newest = [...d.spawned].reverse().find((s) => Object.hasOwn(d.tree.nodes, s));
    if (newest) maxDepth = Math.max(maxDepth, depthOf(d.tree, newest));
    if (d.tip !== null) maxDepth = Math.max(maxDepth, depthOf(d.tree, d.tip));
  }
  return { violations: [], maxDepth };
}

/** Greedy one-op deletion until no single deletion keeps the failure. */
function shrink<T>(seq: readonly T[], fails: (s: readonly T[]) => boolean): T[] {
  let cur = [...seq];
  let progress = true;
  while (progress) {
    progress = false;
    for (let i = cur.length - 1; i >= 0; i--) {
      const cand = [...cur.slice(0, i), ...cur.slice(i + 1)];
      if (fails(cand)) {
        cur = cand;
        progress = true;
      }
    }
  }
  return cur;
}

interface TwoDeviceCase {
  base: Choice[];
  remote: Choice[];
  local: Choice[];
}

function drawTwoDevice(seed: number): TwoDeviceCase {
  const rng = makeRng(seed);
  const draw = (max: number) => {
    const n = rng.int(0, max);
    const out: Choice[] = [];
    for (let i = 0; i < n; i++) out.push(drawChoice(rng));
    return out;
  };
  return { base: draw(20), remote: draw(TWO_DEVICE_MAX_LENGTH), local: draw(TWO_DEVICE_MAX_LENGTH) };
}

const ALLOWED_DROP_REASONS = new Set(["tab_not_open", "unknown_tab", "not_closed_by_token", "no_children"]);

/** Base -> two devices -> remote PUT wins -> local 409 -> rebase -> PUT. */
async function runTwoDevice(c: TwoDeviceCase): Promise<{ violations: string[]; dropped: number; renumbered: number }> {
  const server = createInMemoryTabTreeAdapter();
  const pool: number[] = [];
  const opCount = c.base.length + c.remote.length + c.local.length;
  for (let i = 0; i < opCount; i++) pool.push((await server.allocate("ws", MOTHERSHIP)).public_number);
  let taken = 0;
  const alloc: Allocator = { take: () => pool[taken++] };
  const bail = (where: string, why: string) => ({ violations: [`${where}: ${why}`], dropped: 0, renumbered: 0 });

  let base = newDevice(emptyTabTree(MOTHERSHIP), "b");
  for (const ch of c.base) {
    const r = applyChoice(base, ch, alloc);
    if (r.violations.length > 0) return bail("base", r.violations.join("; "));
    base = r.device;
  }
  const first = await server.save("ws", MOTHERSHIP, toSnapshot(base.tree));
  if (first.status !== "saved") return bail("base save", JSON.stringify(first));

  const loaded = await server.load("ws", MOTHERSHIP);
  const fresh = (prefix: string): Device => {
    const t = fromSnapshot(JSON.parse(JSON.stringify(loaded)));
    if (!t.ok) throw new Error(t.error.message);
    return { ...newDevice(t.tree, prefix), spawned: [...base.spawned] };
  };
  let remote = fresh("r");
  let local = fresh("l");
  for (const ch of c.remote) {
    const r = applyChoice(remote, ch, alloc);
    if (r.violations.length > 0) return bail("remote", r.violations.join("; "));
    remote = r.device;
  }
  for (const ch of c.local) {
    const r = applyChoice(local, ch, alloc);
    if (r.violations.length > 0) return bail("local", r.violations.join("; "));
    local = r.device;
  }

  const out: string[] = [];
  const remoteSave = await server.save("ws", MOTHERSHIP, toSnapshot(remote.tree));
  if (remoteSave.status !== "saved") return bail("remote save", JSON.stringify(remoteSave));
  // Every save bumps the version, so the local PUT must now 409.
  const localSave = await server.save("ws", MOTHERSHIP, toSnapshot(local.tree));
  if (localSave.status !== "conflict") return bail("local save", `expected 409, got ${localSave.status}`);
  const current = fromSnapshot(JSON.parse(JSON.stringify(localSave.current)));
  if (!current.ok) return bail("409 current", current.error.message);
  const remoteTree = deepFreeze(current.tree);
  const rb = rebase(remoteTree, local.pending);

  out.push(...checkInvariants(rb.tree).map((v) => `rebased: ${v}`));
  // Remote numbers are authoritative: nothing the remote holds may move.
  out.push(...stabilityViolations(remoteTree, rb.tree).map((v) => `vs remote: ${v}`));
  out.push(...numberReuse(remoteTree, rb.tree).map((v) => `vs remote R3-1: ${v}`));
  out.push(...counterViolations(remoteTree, rb.tree).map((v) => `vs remote: ${v}`));
  // Synced tabs keep their numbers relative to the local view too; only
  // pending local spawns may be renumbered (R3-5).
  const pendingSpawns = new Set(local.spawned.filter((id) => !base.spawned.includes(id)));
  out.push(...stabilityViolations(local.tree, rb.tree, pendingSpawns).map((v) => `vs local: ${v}`));
  // A local spawn is never lost, and one open locally stays open.
  for (const id of pendingSpawns) {
    const known = Object.hasOwn(rb.tree.nodes, id) || Object.hasOwn(rb.tree.history, id);
    if (!known) out.push(`lost local spawn ${id}`);
    if (Object.hasOwn(local.tree.nodes, id) && !Object.hasOwn(rb.tree.nodes, id)) out.push(`local spawn ${id} open locally but closed after rebase`);
  }
  for (const d of rb.dropped) {
    if (d.op.type === "spawn") out.push(`spawn dropped: ${d.reason}`);
    if (!ALLOWED_DROP_REASONS.has(d.reason)) out.push(`unexpected drop reason ${d.reason}`);
  }
  // The rebased snapshot must be accepted by a server that refuses reuse.
  const retry = await server.save("ws", MOTHERSHIP, toSnapshot(rb.tree));
  if (retry.status !== "saved") out.push(`rebased save: ${JSON.stringify(retry)}`);
  return { violations: out, dropped: rb.dropped.length, renumbered: rb.renumbered.length };
}

describe("tab tree: seeded random sequences", () => {
  it(`${RANDOM_SEQUENCES} single-device sequences of length 1..${RANDOM_MAX_LENGTH} hold every invariant (seed ${SEED})`, () => {
    let ran = 0;
    let steps = 0;
    let maxDepth = 0;
    for (let i = 0; i < RANDOM_SEQUENCES; i++) {
      const seed = SEED + i;
      const seq = drawSequence(seed, RANDOM_MAX_LENGTH);
      const r = runSingle(seq);
      ran++;
      steps += seq.length;
      maxDepth = Math.max(maxDepth, r.maxDepth);
      if (r.violations.length > 0) {
        const minimal = shrink(seq, (s) => runSingle(s).violations.length > 0);
        expect.fail(`seed ${seed} (sequence ${i}) failed: ${r.violations.join("; ")}\nshrunk to ${minimal.length} ops: ${JSON.stringify(minimal)}\n=> ${runSingle(minimal).violations.join("; ")}`);
      }
    }
    console.info(`[tabTree random] single-device: sequences=${ran} steps=${steps} maxDepth=${maxDepth}`);
    expect(ran).toBe(RANDOM_SEQUENCES);
  }, 120_000);

  it(`${TWO_DEVICE_RUNS} two-device runs rebase through a 409 without reuse or a lost spawn (seed ${SEED})`, async () => {
    let ran = 0;
    let dropped = 0;
    let renumbered = 0;
    for (let i = 0; i < TWO_DEVICE_RUNS; i++) {
      const seed = SEED + 100_000 + i;
      const c = drawTwoDevice(seed);
      const r = await runTwoDevice(c);
      ran++;
      dropped += r.dropped;
      renumbered += r.renumbered;
      if (r.violations.length > 0) {
        expect.fail(`seed ${seed} (run ${i}) failed: ${r.violations.join("; ")}\ncase: ${JSON.stringify(c)}`);
      }
    }
    console.info(`[tabTree random] two-device: runs=${ran} droppedOps=${dropped} renumberedSpawns=${renumbered}`);
    expect(ran).toBe(TWO_DEVICE_RUNS);
    // Guard against a vacuous suite: both rebase paths really ran.
    expect(dropped).toBeGreaterThan(0);
    expect(renumbered).toBeGreaterThan(0);
  }, 120_000);

  it(`${DEEP_SEQUENCES} chain-biased sequences of length ${DEEP_LENGTH} reach depth >= ${DEEP_TARGET_DEPTH} and hold every invariant`, () => {
    let maxDepth = 0;
    let reached = 0;
    for (let i = 0; i < DEEP_SEQUENCES; i++) {
      const seed = SEED + 200_000 + i;
      const seq = drawSequence(seed, DEEP_LENGTH, DEEP_CHAIN_BIAS, true);
      const r = runSingle(seq);
      maxDepth = Math.max(maxDepth, r.maxDepth);
      if (r.maxDepth >= DEEP_TARGET_DEPTH) reached++;
      if (r.violations.length > 0) expect.fail(`seed ${seed} (deep ${i}) failed: ${r.violations.join("; ")}`);
    }
    console.info(
      `[tabTree random] deep: sequences=${DEEP_SEQUENCES} length=${DEEP_LENGTH} maxDepth=${maxDepth} reachedDepth${DEEP_TARGET_DEPTH}=${reached}`,
    );
    expect(maxDepth).toBeGreaterThanOrEqual(DEEP_TARGET_DEPTH);
  }, 120_000);
});

describe("strictSame agrees with toStrictEqual on tab trees", () => {
  it("rejects what toStrictEqual rejects and accepts a real round trip", () => {
    expect(strictSame({ a: 1 }, { a: 1, b: undefined })).toBe(false);
    expect(strictSame({ a: [1, 2] }, { a: [1, 2, 3] })).toBe(false);
    expect(strictSame({ a: "1" }, { a: 1 })).toBe(false);
    expect(strictSame([], {})).toBe(false);
    expect(strictSame({ a: { b: null } }, { a: { b: null } })).toBe(true);
    let t = emptyTabTree(MOTHERSHIP);
    for (let i = 1; i <= 30; i++) {
      const parent = i === 1 ? null : `t${Math.ceil(i / 3)}`;
      const r = spawnChild(t, parent, { tab_id: `t${i}`, kind: "reader", ref: `doc-${i}`, mothership: MOTHERSHIP });
      if (!r.ok) throw new Error(r.error.message);
      t = r.tree;
    }
    const back = fromSnapshot(JSON.parse(JSON.stringify(toSnapshot(t))));
    if (!back.ok) throw new Error(back.error.message);
    expect(back.tree).toStrictEqual(t);
    expect(strictSame(back.tree, t)).toBe(true);
    const c = closeTab(t, "t2", "lift_children", "now");
    if (!c.ok) throw new Error(c.error.message);
    let toStrictSaysEqual = true;
    try {
      expect(c.tree).toStrictEqual(t);
    } catch {
      toStrictSaysEqual = false;
    }
    expect(strictSame(c.tree, t)).toBe(toStrictSaysEqual);
  });
});
