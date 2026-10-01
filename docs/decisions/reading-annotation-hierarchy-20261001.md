# Reading annotations: meaning, importance, and brackets

Date: 2026-10-01. Handoff for Antiek's UI design agent. The operator confirmed the strongest question treatment on this date.

## Scope and status

These requirements apply to the reading UI. The approved mascot remains original coral with full magenta legs and warm brown-red contours. Its palette does not determine annotation meaning.

This document captures the operator's design requirements. The importance classifier and bracket interactions need a design proposal before implementation. The reading-comfort theme release should not ship an interim manual color picker as the finished annotation system.

## The annotation language

| Meaning | Importance | Treatment | Exact pigment |
| --- | --- | --- | --- |
| Information or insight | Context | Black bracket | `#1A2E21` |
| Information or insight | Notable | Black underline | `#1A2E21` |
| Information or insight | Major | Lime highlight | `#A9FF17` |
| Open question or perplexity | Context | Magenta bracket | `#943D4A` |
| Open question or perplexity | Notable | Magenta underline | `#943D4A` |
| Open question or perplexity | Major | Magenta underline plus magenta bracket | `#943D4A` |

The information hierarchy increases from black bracket to black underline to lime highlight. The brackets are the lightest emphasis. This is a hierarchy of importance, not three decorative color choices.

The question hierarchy increases from magenta bracket to magenta underline to magenta underline plus magenta bracket. Use `#943D4A` for every question tier. A major unresolved question receives the combined underline and bracket, never lime. A filled magenta highlight is not an approved treatment.

## Determine treatment from the reader's writing

The prompt written by the reader should determine the annotation's meaning and treatment. The reader should not have to choose a color first.

- A prompt that identifies an open question or something perplexing belongs to the magenta question branch.
- A note such as "This is interesting because...", without a separate question or research prompt, normally receives a black underline.
- A note can still become a lime highlight when the insight is very important. Having no separate prompt does not limit it to black.
- The system must assess the importance of the actual insight to distinguish black underline from lime highlight. The presence of a note, its length, or the word "interesting" alone is not sufficient.
- Lower-priority important information belongs at the black bracket level.

The operator has not yet defined scoring criteria, thresholds, a model, or a review mechanism for importance. The design agent should propose these explicitly. Do not ship a keyword rule as if it implements an assessment of insight.

## Scope is separate from importance

Support both paragraph and sentence scopes at each applicable level.

- **Paragraph or section:** draw a bracket beside the paragraph or selected section.
- **Sentence range:** bracket the beginning and end of one, two, or three sentences without bracketing the entire paragraph or section.
- Apply the same scope distinction to the magenta question/perplexity branch.

Do not promote a mark's importance merely because it covers more text. A bracketed paragraph can be less important than a highlighted sentence. The reader's intended sentence range must survive wrapping, pagination, and reopening.

## Design proposal needed

The following are proposed design questions, not additional approved requirements:

1. How should the system assess an insight's importance in relation to the reader's current reading or research goal?
2. If a prompt contains both a valuable insight and a question, should those become separate annotations, or one annotation with two meanings?
3. How does the reader correct the inferred meaning, importance, or scope, and how are those corrections retained? The reader's correction must win over an automatic suggestion.
4. How should a classifier express uncertainty without inventing a confident importance judgment?
5. How can exact black and magenta remain visible in the night theme? Both pigments need a contrast treatment on the existing dark reading page. Evaluate a narrow neutral backing or another unobtrusive treatment without recoloring the prose.
6. How do brackets behave when their paragraph or sentence range crosses a page boundary, contains a link, or partially overlaps another annotation?

## Suggested data model for the proposal

Keep the following concepts distinct. These are design suggestions pending the agent's proposal:

- Canonical passage anchor and document identity.
- Meaning: information/insight versus question/perplexity.
- Importance level, distinct from meaning and passage length.
- Scope: paragraph/section versus an explicit sentence range.
- The reader's prompt or note that motivated the classification.
- Classification result, its basis, confidence, and any reader correction.
- Display treatment derived from meaning and importance, rather than a free-form stored hex.

Use the existing persisted anchor and rights boundaries. Existing annotations need an explicit compatibility policy. Automatic research/Note actions must not silently overwrite a reader's annotation classification.

## Review examples

| Reader's writing and selection | Expected interpretation |
| --- | --- |
| "I don't understand why this follows" on one sentence | Question/perplexity, magenta emphasis; underline is the specified treatment. |
| "This is interesting because it explains the earlier example" | Normally notable information, black underline. |
| A note explaining a central insight that changes the reader's understanding | Evaluate for super notable information, lime highlight; establish and explain the importance criterion. |
| A useful contextual paragraph that does not deserve an underline | Black paragraph-side bracket. |
| Two useful sentences within a larger paragraph | Black brackets at the beginning and end of those sentences, rather than the whole paragraph. |
| A paragraph containing an unresolved question of lower emphasis | A magenta paragraph bracket. |
| "Without resolving this contradiction, I cannot accept the central conclusion" on two selected sentences | A major unresolved question, with magenta underline plus magenta brackets at the selected endpoints. It never receives lime. |

The UI design agent should return light/night and narrow-screen mockups, the classification decision rules, bracket geometry, and examples of ambiguous prompts. The operator's book-like, quiet reading experience remains the design constraint.

The six treatments are the confirmed visual contract. Implementation still needs the owners' agreement on revision and request-generation invalidation; separate durable note history and anchor association; metadata-only audit with private owner-gated evidence; current source revision and rights at dispatch, acceptance and render; ordered validated node ranges; and paragraph and sentence brackets in both plain and HTML reading, including reflow, overlap and accessibility. This decision does not approve an API shape, classifier, persisted lifecycle or renderer.
