# Competitive deep-research landscape → Antiek execution map

**Date:** 2026-07-09  
**Status:** living decision notes (not auto-code)  
**Audience:** future agents executing residual (ap+) on PR #465 / research-reading spine  
**Bar:** technical precision; hard-to-vary craftsmanship; five values  

---

## 1. Why this note exists

Operator north star: **highest-quality deep research product in the world**, with:

- research workstation that records insights/questions recursively  
- reading = research (HTML-first assets)  
- floating deep-research from highlights  
- merge draft before full parent commit  
- multi-spawn collective research  
- recursive twin notes  
- Midnight Oil autonomous mode  
- arxiv/substack (and other knowledge-dense pubs) as first-class references  
- model decision-tree + budget projection + Antiek-bench recursive rewrite  

This document studies **what competitors optimize for**, maps Antiek gaps honestly against **shipped PR #465 substrate**, and defines **executable residuals** so agents do not rebuild living-roadmap mirages.

---

## 2. Competitor posture (public product behavior, not reverse-engineered IP)

| Product | Strength | Weakness vs Antiek north star | Technical implication for us |
|---|---|---|---|
| **OpenAI Deep Research** | Multi-step long-horizon synthesis; high depth; strong source synthesis | Opaque workspace; not a personal knowledge graph; limited dual “twin notes”; not HTML-first personal corpus | Match **depth + evidence discipline**, not chat-shell UX. Keep twin + graph + HTML assets as differentiators. |
| **Perplexity Deep Research** | Speed; clear citations; API-friendly; good “answer+sources” loop | Session-centric; weak recursive personal memory; no reading/book host | Match **citation density + latency tiers**. Antiek should offer flash/pro depth tiers (decision-tree already exists). |
| **Gemini Deep Research** | Workspace integration (Drive/Gmail/Docs); multi-page reports | Ecosystem lock-in; not operator-owned corpus; not custom model portfolio | Match **artifact quality**; Antiek wins with **owned HTML library + marketplace host + engagement spine**. |
| **Claude Projects / long-context** | Patient long docs; project memory | Not multi-spawn floating windows; not graph promote | Match **long-context wrestle**; use twin promote into graph for durable memory beyond project files. |
| **Elicit / Consensus / academic tools** | Paper-native workflows; structured extraction | Narrow domain; not general reading+writing workstation | Antiek arxiv attach + book marketplace should be **as good as academic tools for papers**, without leaving the workstation. |
| **NotebookLM** | Source-grounded notebook from uploaded docs | Closed sources; not infinite platform; not agent swarm | Twin notes + research context pack are Antiek’s answer to “notebook over sources.” |
| **Generic agent swarms** | Parallel subagents | Weak product UX for merge/draft/collective | Midnight Oil + floating sessions + collective merge UI (an/ao) are Antiek’s productization of swarm research. |

### Shared technical decisions across leaders

1. **Plan → browse/gather → synthesize → cite** loop (not single-shot chat).  
2. **Multi-minute jobs** with progress/status (Antiek: Midnight Oil job + ceiling).  
3. **Source identity** as first-class (urls, paper ids) — Antiek: `source_refs` arxiv/substack/url.  
4. **Human-readable report artifact** — Antiek must remain **HTML-first** (`view_format=html`), never PDF-required.  
5. **Model specialization** — leaders pin one lab model; Antiek differentiates with **operator model choice + Antiek-bench recursive task classes**.

### What leaders do *not* do (our wedge)

- Personal **depth graph** of insights/questions with promote writers.  
- **Twin document** per asset (LLM as permanent note-taker).  
- **Highlight → floating panel → full → merge draft → merge parent**.  
- **Collective multi-spawn** selection UI into one unit *and* draft document.  
- **Operator budget projection** before a prompt burns the cap.  
- **Recursive bench** that proposes suite deltas from real usage (propose ≠ auto-promote).  
- **NotDiamond authority** rejected; advisory only (ak).  

---

## 3. Antiek inventory reality (PR #465 campaign, post ao)

**Branch of record:** `campaign/research-reading-spine-2026-07-09-main`  
**Do not rebuild** living-roadmap SPR-01..14 or substrate packages already `branch_only`.

| Capability | Status on campaign branch | Competitor parity note |
|---|---|---|
| Engagement spine spawn/twin/merge/collective | shipped | Exceeds chat products on structure |
| Floating session + window host | shipped | UI productization of multi-window research |
| ResearchContextPanel + Collective merge UI | shipped (ao) | Wedge vs Perplexity/OpenAI single-thread |
| merge draft_combined product path | shipped (an) | Matches “draft before commit” reading workflow |
| Midnight Oil product path | shipped | Autonomous mode ≠ competitor web-only DR |
| Marketplace host + HTML view | shipped | Book host wedge |
| Source refs arxiv/substack | shipped (attach) | **Gap:** live fetch/normalize into HTML asset |
| Antiek-bench propose + Settings approve | shipped (al/am) | Unique vs competitors |
| NotDiamond | advisory only | Correct under §16 |
| HTML-first projection | on_main + branch | Non-negotiable |

---

## 4. Residual backlog for future agents (ordered)

Residuals are **one product seam each**. Status values: `missing` | `branch_only` | `spec_only`.

### (ap) THIS DOC — competitive notes + execution map  
**Status:** `branch_only` after ship of this file.  
**Done when:** VERDICT.md exists with competitor table + ordered residuals + non-goals.

### (aq) Live publication hydrate (arxiv/substack → HTML asset)  
**Why:** attach-refs parse identity but do not fetch body into HTML-first library.  
**Seam:** compose existing acquisition/arxiv (or thin offline-friendly stub) + `host_into_account`-style HTML projection; product entry POST `/engagement/hydrate-ref`.  
**Non-goal:** full PDF pipeline as primary view.

### (ar) Research progress telemetry for multi-minute jobs  
**Why:** competitors show multi-step progress; Midnight Oil has job status but workstation deep research needs step events.  
**Seam:** event list on spawn/session (`plan`, `gather`, `synthesize`, `cite`) offline-recordable.

### (as) Evidence pack product surface  
**Why:** OpenAI/Perplexity win on citation trust.  
**Seam:** HTML evidence section from source_refs + twins; mount under ResearchContextPanel.

### (at) Depth-tier presets in decision-tree  
**Why:** Perplexity speed vs OpenAI depth is a product choice.  
**Seam:** Settings presets `flash | pro | wrestle` mapping to model_id + expected cost projection (#440).

### (au) Midnight Oil → engagement deposit polish  
**Why:** autonomous mode must land twins + refs into graph like interactive path.  
**Seam:** ensure deposit path records usage_bridge events (already partial).

### (av) Competitive dogfood harness (offline fixtures)  
**Why:** weekly Antiek-bench should include DR task classes against fixed fixtures.  
**Seam:** suite items in `book_qa` / `wrestle` from usage rewrite (al/am already enable propose).

---

## 5. Non-goals (hard)

- Becoming a thin wrapper around a single vendor Deep Research API as the product.  
- NotDiamond as §16 dispatch authority.  
- Auto-promote Antiek-bench suite without Settings approve.  
- PDF as required human view surface.  
- Re-executing living-roadmap SPR-01..14.  
- Operator merge to main (PR only).  

---

## 6. Execution contract for next agent

1. Inventory vs `origin/main` + PR #465 tip; mark (a)–(ap) with single status each.  
2. Pick **one** residual from §4 (recommended: **aq** hydrate-ref if acquisition exists, else **as** evidence pack).  
3. Thin product path over shipped functions; real tests offline; HTML-first.  
4. Ledger entry; push campaign branch; do not merge main.  
5. Re-derive next residual from this map + north star.

---

## 7. Citations / sources (public product comparisons)

Industry comparisons of OpenAI vs Perplexity vs Gemini Deep Research emphasize depth vs speed vs workspace integration; academic tools emphasize paper structure. Treat public writeups as **posture signals**, not internal architecture truth. Verify any implementation claim against Antiek code before coding.
