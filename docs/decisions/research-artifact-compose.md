# Research artifact compose — ANT-AHT SPR-AHT-05

Merge semantics: **graph/pack first**; HTML compose is an index linking member artifacts. Hash collisions surface in the compose page — not silent git-merge of HTML bodies.

CLI: `python -m substrate.research_artifact id1 id2 --compose`

## Source/twin apply boundary

SPR-AHT-05 compose and the Reader review packet are **not** a source-book or
twin-document mutation. The reviewed apply step is specified separately in
`docs/htmlspec/antiek-html-transport/sprint-08-source-merge-apply.html`.

Until that sprint is implemented, no UI or API should claim that a draft merge
has been merged into the source book or promoted into its notes twin. The apply
boundary must require an operator acknowledgement, refuse stale review packets,
surface hash conflicts, and return an explicit mutation receipt.
