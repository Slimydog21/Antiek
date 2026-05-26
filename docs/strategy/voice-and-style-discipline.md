# Voice and Style Discipline

**Status**: substrate prompt engineering — load-bearing for product quality
**Affects**: every role that produces operator-facing output (synthesizer,
  evidence_retriever, note_taker, eventually creation-surface roles)
**First implementation**: Sprint 11 (alongside the web app MVP)

---

## The problem

Default LLM output has a recognizable shape:

- Em-dashes everywhere (the unmistakable sign of GPT-class autoregressive prose)
- Bullet-point staccato structure ("Here are 3 things: 1, 2, 3")
- Same flow every time regardless of subject matter
- Generic AI English vocabulary (every sector reads identical)
- Padding sentences that announce what's coming ("It's important to note that...")
- Hedging modifiers that undermine claims ("It could be argued that...")
- The em-dash–laden three-clause sentence is the signature

Operator's framing: *"this thing is naturally not the deliverables, not
human written. But to eliminate the robotic nature of the output and that
every output has the same flow of like bullet point, bullet point, bullet
point inside twine 234 question, question question. There should be a more
fluid linguistic approach where the structure should be. Here are the
takeaways and here are the questions. But the writing and the evidence and
the data that kind of goes within each of those, it's something that needs
to be technically brainstormed through to kind of maintain a high quality
of information."*

The bet: **reading-for-understanding has a different cognitive shape than
reading-for-compliance.** A research thesis that reads like a McKinsey deck
fails its job even if every fact is correct. The reader's brain registers
the slop and downshifts into skim mode. The substrate has to produce
output that the reader *wants* to engage with at the prose level.

---

## What the substrate currently does wrong

As of Sprint 10 the synthesizer prompt
(`roles/synthesizer/prompt.py`) explicitly instructs structured JSON
output. The MASTER.md template
(`skills/domain/master_md.py:generate_master_md`) renders that JSON
into a rigid section structure:

```
## Thesis Summary
## Thesis Components
### Component 1
### Component 2
## Falsification Conditions
## Execution Risks
```

This is the right *structure* for an evidence-trail audit. It is the
wrong *reading experience* for a person who wants to think alongside
the synthesis.

The evidence_retriever prompt (`roles/evidence_retriever/prompt.py`)
demands structured JSON with `supporting_claims`, `evidentiary_gaps`,
`source_tier_min`, etc. The role plays it safe and produces sterile
clause-by-clause language because the structured-output instruction
implicitly rewards mechanical text.

Concrete artifacts of the failure mode appear in the local validation
runs:

- "Tier-2 textbook reporting indicates that adaptive filtering
  algorithms applied to DPI/clutter cancellation in passive radar
  include LMS, NLMS, RLS..." — reads like a procedurally-generated
  literature index, not like a researcher's notebook
- Falsification conditions phrased as "The claim X would be falsified
  if Y observable" — correct logically, robotic linguistically

---

## What "good" looks like

A thesis that:

1. **Absorbs the source corpus's vocabulary.** Radar engineers say
   "sidelobe level reduction" not "noise floor improvement." VC analysts
   say "moat" not "competitive advantage." Sector vocabulary is the
   surface marker of subject-matter fluency; using the generic
   superordinate term marks the output as outsider-written.
2. **Reads like a researcher's notebook entry.** Specific claims with
   numbers. Acknowledged uncertainty. Connections between ideas drawn
   in-line rather than enumerated.
3. **Preserves structural distinction** between insights (this is
   established) and open questions (this is unresolved) — that
   structural distinction is load-bearing for the substrate's recursive
   chase mechanic. But the prose within each section is *flowing*, not
   list-bulleted.
4. **No em-dashes except where a writer with a strong style would use
   one** (rare; ~1 per page max).
5. **No padding sentences.** "It's worth noting that," "It is important
   to recognize that," "In conclusion, we can see that" all banned.
6. **Confidence is conveyed by sentence rhythm and word choice**, not
   by appending "(high confidence)" markers everywhere. The
   substrate already carries confidence as structured metadata; the
   prose doesn't need to re-state it.

A good rough comparator: New Yorker long-form journalism. The structure
is there but invisible; the prose moves; the vocabulary fits the
subject; the reader trusts the writer's eye.

---

## Canonical machine source (drift prevention — Sprint 11)

This document is the **design authority** for the discipline. The
**canonical machine source** the roles actually consume is
`substrate/voice_style/constructions.py`. It expresses the §5 forbidden
constructions + permitted-construction guidance once, as data, with
`render_voice_addendum(register=...)` composing the per-role prompt
addendum text. The synthesizer and evidence_retriever render their
addendum from it (registers `"synthesizer"` and `"evidence_retriever"`);
the creative_writer and interviewer reference it as the named authority
and are guarded by `tests/test_voice_style_constructions.py` so their
register-specific framing cannot silently drop a canonical construction.

**Why this exists:** before Sprint 11 the forbidden-construction list was
copy-pasted inline across four role prompts plus the autoresearch scorer.
Four copies drift — and they had already begun to (different surfaces
banned different phrases). One source the roles reference prevents the
silent divergence that lets one surface go sloppy while the others stay
disciplined.

**For a future role:** do NOT copy-paste a forbidden list into a new
prompt. Either call `render_voice_addendum(...)` with an existing register,
or, if you need a genuinely different framing, add a register to
`constructions.py` (drawing its forbidden items from
`FORBIDDEN_CONSTRUCTIONS`) so the shared source stays the single point of
truth.

(The deterministic scorer `tools/prompt_autoresearch/score.py` keeps its
own regex list on purpose — it is a tuned measurement of the same §5
discipline, not a prompt; unifying it would change the composite score.
See the comment there.)

## Implementation — substrate-side prompt changes

### Change 1: Synthesizer system prompt addendum

Append to `roles/synthesizer/prompt.py:SYNTHESIZER_SYSTEM_PROMPT`:

```
## Voice and style

Your output is the human-facing deliverable of an entire investigation
chain. It will be read by a person trying to understand a subject, not by
a downstream automated consumer. Optimize the prose for engaged reading,
not for parsing.

Absorb the vocabulary of the source corpus you cite. If the corpus uses
"direct-path interference suppression," do not paraphrase to "signal
cancellation." If the corpus uses sector-specific shorthand, use it (and
expand once on first use). Generic AI English vocabulary is a signal of
subject-matter weakness. Use the field's own words.

Prose, not bullets, within each section. Top-level structure (thesis
summary, thesis components, falsification conditions, execution risks)
stays. Inside each section, write flowing paragraphs, not enumerated
clauses. Components 1, 2, 3 are okay because they correspond to
distinct claims. Each component's body is prose.

Forbidden constructions:
- Em-dashes (use commas, parentheses, or two sentences instead). At
  most one em-dash per thesis if absolutely necessary for a strong
  beat.
- Padding sentences ("It is important to note that," "It is worth
  observing that," "This indicates that").
- Hedging modifiers that undermine claims you have evidence for ("It
  could be argued that," "Some might suggest that"). If the evidence
  supports a claim, say it. If it doesn't, the claim doesn't belong.
- Generic enumeration tics ("Firstly," "Secondly," "Finally,").
- Repetition of confidence levels in prose. The structured metadata
  carries the confidence; the prose carries the substance.

Permitted and encouraged:
- Specific numbers from the corpus, in the corpus's units.
- Sentences with internal logic, not just declarative facts. The
  reader should be able to follow why one claim leads to another.
- Naming primary sources by their distinguishing feature, not just
  their tier ("the Malanowski textbook" beats "a Tier-2 source").
- Acknowledging the boundary of what was retrieved. "The corpus
  surfaced no comparative benchmark across illuminator types" beats
  "this question cannot be answered."
```

### Change 2: Evidence retriever prompt addendum

Append to `roles/evidence_retriever/prompt.py:EVIDENCE_RETRIEVER_SYSTEM_PROMPT`:

```
## Voice for claim text

Each `claim` field is read by a synthesizer downstream AND by a human
in the trajectory view. Write claim text as you would write a research
note for yourself: specific, citing the source's language, avoiding
generic AI vocabulary.

Forbidden in claim text:
- Em-dashes
- "The context indicates that..." preamble. Just state the claim.
- Padding clauses ("It should be noted that...").

A good claim: "Malanowski reports LSL and block-lattice filters
achieve >40 dB sidelobe reduction relative to the DPI peak on real
passive radar data."

A bad claim (current default): "The context indicates that adaptive
filtering algorithms, specifically least-squares lattice (LSL) and
block lattice filters, have been reported to demonstrate sidelobe
level reductions exceeding 40 dB relative to direct-path interference
peaks based on real passive radar dataset evidence."

Same information; first reads like research, second reads like a
parsing artifact.
```

### Change 3: New role — `style_extractor` (optional, feature-flagged)

When investigation context is *qualitative or thematic* (history,
investment thesis, literary criticism, science explanation), reading
the top-K chunks BEFORE synthesis produces a sector-specific style
guide that the synthesizer can absorb.

Pure-quantitative investigations (find me the number, count the
occurrences) don't benefit from this and skip the step.

**Detection heuristic**: if the decomposer's sub-questions contain
>50% questions tagged `parameter_extraction` or `quantitative_metric`,
skip the style extractor. Otherwise run it.

**The role**:

```python
# roles/style_extractor/prompt.py

STYLE_EXTRACTOR_SYSTEM_PROMPT = """
You read N text chunks and produce a brief style guide (~150-300 words)
describing the writing voice, sector vocabulary, and argumentation
patterns characteristic of the source corpus. This guide gets passed
to a downstream synthesizer role; your output influences what its
prose sounds like.

Return JSON with these fields:
- vocabulary: 8-15 sector-specific terms or phrases the corpus uses
  repeatedly. Include the term as written, not your paraphrase.
- argumentation_pattern: 2-3 sentences describing how claims are
  structured in this corpus (e.g., "claims are anchored to specific
  experimental numbers, with hedging reserved for the comparison to
  prior work").
- sentence_rhythm: one sentence describing typical sentence length and
  shape (e.g., "medium-length sentences with one subordinate clause,
  paragraph-final declarative beats").
- forbidden_in_this_register: 2-4 patterns that would mark output as
  out-of-register for this corpus (e.g., "first-person singular
  reflection," "marketing language").
- voice_summary: 1-2 sentences operationalizing the above into a
  prescriptive style note for a writer.
"""
```

**Cost**: one extra flash-tier dispatch per investigation that gets it
(roughly $0.0002). Run before the synthesizer; inject the
`voice_summary` + `vocabulary` into the synthesizer's context pack as a
new layer (kind=`style_guide`, priority similar to `long_term_skill`).

**Verification**: track a `style_extractor_used: bool` field on the
synthesis event. A/B-able later by toggling it on/off across cohort
investigations and reading the outputs.

### Change 4: MASTER.md template restructure

`skills/domain/master_md.py:generate_master_md` currently renders the
full structured payload into a rigid sections cascade. Change to:

- **Thesis summary** stays at top as prose.
- **Thesis components** stay as numbered sections but each renders as
  prose, not as a definition-list of fields. The current rendering
  ("- **Claim:** ... - **Confidence:** ... - **Supporting chunks:** ...")
  becomes a prose paragraph that ends with an inline confidence marker
  and a citation-chip footer rather than a label-value list.
- **Falsification conditions, execution risks, constraint compliance**
  move to a collapsed-by-default appendix at the bottom. They're audit
  metadata, not reading material. The MasterMdViewer renders them
  under a `<details>` element.
- **Recommendation** stays as a banner near the top.

The structured Pydantic payload doesn't change. Only the rendering
template changes.

---

## Implementation — UI-side rendering choices

The web app MUST respect the prose-first discipline:

1. **Reading typography.** MasterMdViewer uses a serif body font
   (Charter, Iowan Old Style, system serif). The trajectory view and
   sidebars can stay sans-serif. The serif font signals "this is for
   reading, not for scanning."
2. **No forced bullets in prose blocks.** If react-markdown encounters
   a paragraph that starts with "•" or "1." (which the model
   occasionally inserts despite the prompt), the renderer strips them
   and renders as flowing prose. Defensive against prompt non-compliance.
3. **Claim spans are inline** — `<span data-claim-id>` not `<li>`.
   Hovering reveals citations as a tooltip; click expands to the
   chunk modal.
4. **Appendix material collapsed.** Falsification + execution risks +
   constraint compliance default to `<details>` elements, closed.
   The primary reading flow is the thesis prose.
5. **No "AI is thinking" animations.** The trajectory view shows
   actual phase progression. No spinning robot icons, no anthropomorphic
   "let me think about that..." copy. Treat the user as someone who
   wants information, not theater.

---

## Verification

How to tell if this works:

1. **Read a real MASTER.md output and notice if it reads like an
   article.** If you find yourself skimming, the prose is wrong. If
   you find yourself slowing down to absorb a sentence, the prose is
   right. This is the primary qualitative test.
2. **Grep for em-dashes**: `grep -c "—" MASTER.md`. Target: ≤2 per
   thesis. Currently averaging 12-20 per thesis (Sprint 10 outputs).
3. **Grep for padding constructions**: count occurrences of "It is
   important to note", "It should be observed", "It can be argued
   that". Target: 0.
4. **Sector vocabulary check**: pick 5 corpus chunks at random,
   identify 3 sector-specific terms in each. Check whether those
   terms appear in the synthesis output. Target: synthesis uses ≥40%
   of identifiable sector terms.
5. **A/B test**: run the same cold question with `style_extractor`
   on vs off. Read both outputs. If the operator can't reliably tell
   which is which after a few minutes, the style_extractor isn't
   earning its keep and gets removed.

---

## Open questions

- **Does the style discipline apply to the note_taker role?** That role
  produces the live "notes from this wrestling event" text that appears
  in the NotesFeed. Probably yes, but note-taker output is shorter and
  more telegraphic by nature. Less prose-flow, more crystallization.
  Defer answering until Sprint 11 ships.
- **Does the discipline apply to the decomposer's sub-questions?**
  Sub-questions are questions, not prose. The discipline applies in
  the sense of "avoid generic AI question constructions" ("To what
  extent does X impact Y?" is slop). But the structural form is fixed
  (it's literally a list of questions). Lighter discipline; capture
  in the decomposer prompt's existing anti-patterns list.
- **What about the connector role?** Connector outputs cross-domain
  mappings — structured edges between nodes. Less prose-heavy. Style
  discipline applies to any natural-language explanation text the
  connector produces (currently minimal). Lower priority.
- **Long-term: does the substrate need a "style policy" config**, the
  way it has a "dispatch policy" config in `substrate/dispatch/config.yaml`?
  Probably eventually. Per-investigation style overrides would let the
  operator say "write this thesis in a more clinical voice" or "write
  this for a non-expert audience." Defer until the basic discipline lands.
