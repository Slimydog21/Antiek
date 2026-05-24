/**
 * Mock paste blocks for Storybook + tests. Deliberately diverse.
 */

import type { ResearchBlockSummary } from "./types";

export const MOCK_BLOCKS: ResearchBlockSummary[] = [
  {
    document_id: "doc-72f433b8fafc6a5e",
    source: "anthropic",
    source_confidence: 0.83,
    paste_byte_length: 2750,
    operator_label: "Prime Intellect substrate landscape",
    session_id: "S-prim-thesis",
    pasted_at: "2026-05-24T16:56:14",
    title: "The on-policy RL market has fragmented into three identifiable layers",
    insight_count: 3,
    open_question_count: 2,
  },
  {
    document_id: "doc-1a23bc44d5e6f789",
    source: "alphasense",
    source_confidence: 0.91,
    paste_byte_length: 3420,
    operator_label: "PRIM Q3 2024 — sell-side mix",
    session_id: "S-prim-thesis",
    pasted_at: "2026-05-24T17:12:08",
    title: "Prime Intellect Inc (NASDAQ: PRIM) — Q3 2024 Earnings Call Analysis",
    insight_count: 5,
    open_question_count: 1,
  },
  {
    document_id: "doc-3c45de77a8b9c012",
    source: "chatgpt",
    source_confidence: 0.71,
    paste_byte_length: 1860,
    operator_label: null,
    session_id: "S-prim-thesis",
    pasted_at: "2026-05-24T17:34:22",
    title: "Deep research: the on-policy RL market for code agents, 2024-2026",
    insight_count: 4,
    open_question_count: 3,
  },
  {
    document_id: "doc-9f87ed66c5d4b321",
    source: "grok",
    source_confidence: 0.66,
    paste_byte_length: 1280,
    operator_label: "X-platform sentiment check",
    session_id: null,
    pasted_at: "2026-05-23T19:02:55",
    title: "TL;DR: The on-policy RL market for code agents has split into three layers",
    insight_count: 2,
    open_question_count: 2,
  },
  {
    document_id: "doc-aabbccdd11223344",
    source: "other",
    source_confidence: 0.32,
    paste_byte_length: 940,
    operator_label: "ambiguous source — manual override",
    session_id: null,
    pasted_at: "2026-05-23T21:18:01",
    title: "Notes from a personal blog post on RL substrate plays",
  },
];
