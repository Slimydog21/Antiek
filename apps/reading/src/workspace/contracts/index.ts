/**
 * contracts/index.ts — the SPR-06 contract module. LAZY module: entry-chunk
 * code imports `type` from `./contracts/tree` or `./contracts/anchor`
 * directly, or dynamic-imports this index the way shortcuts.ts:320-322
 * imports companionStore. Nothing from `adapters/` is re-exported here: a
 * feeder is mounted once at the consumer root (SPR-04) and deleted by one
 * edit (CONTRACTS.md §3); consumers never name it.
 */
export * from "./tree";
export * from "./anchor";
export * from "./selection";
export * from "./treeStore";
export * from "./openers";
