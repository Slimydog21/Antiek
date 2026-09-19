REWORK ROUND for SPR-07 (branch drd/spr07-acquisition-repair). Adversarial review verdict: REWORK — findings 1-2 MAJOR (mandatory), 3-6 MINOR (all cheap; fix all). All fixes are test-side or tiny client additions.

FINDING 1 (MAJOR): the no-live-network socket guard exists only in tests/test_oai_pmh.py. Replicate the guard fixture (autouse) into tests/test_openalex.py, tests/test_s2_enrich.py, tests/test_substack_feed.py. DO NOT touch tests/conftest.py — it is outside this lane's owned files (seam violation). A small duplicated fixture in each owned file is the correct move here.

FINDING 2 (MAJOR): Substack archive-paging (the offset += limit backfill loop, client.py:79-81) is never exercised — the fixture returns one short page so the loop exits immediately. Add a multi-page archive fixture (page sizes == limit, then a short page) asserting the client requested offset=0, offset=limit, offset=2*limit and aggregated all items.

FINDING 3 (MINOR): OpenAlex rate-ceiling test must SPY that get was NOT called on the raising request (call-count assertion), mechanically proving raise-before-HTTP.

FINDING 4 (MINOR): add the authenticated S2 path test (key present → x-api-key header sent) and assert the key does not appear in repr(client) or str(client).

FINDING 5 (MINOR): add one Substack 429/Retry-After test proving the shared BanSentinel discipline applies (persisted sentinel refuses a second client instance, same shape as the OAI test).

FINDING 6 (MINOR): OpenAlex tracks per-second ceiling but not the documented daily bound. Add a day-window counter with a red-proof, OR a cited comment + handoff entry explaining why per-second alone is the honest interpretation. Your call — but decide explicitly, do not ignore.

Then re-run ALL gates until green (pytest all four test files; mypy --strict on the four packages; ruff over every owned file including all four test files). Update HANDOFF-SPR07.md from fresh verbatim outputs (the current M4 claim mildly overclaims — correct it). Logical commits, no push. Do not commit SPEC-SPR07.html, REWORK-BRIEF.md, or .venv-wt.
