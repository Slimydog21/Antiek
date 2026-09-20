# Research-only principal / owner BYOT audit

Read-only production review at /Users/slimydog/Antiek/worktrees/research-only-principal-split, baseline 560e46267. No production edits, network, credential reads, or real provider calls.

## Confirmed source flow

Research-only raw text reaches the owner BYOT dispatch boundary. Reproducer `/tmp/test_principal_byot_probe.py`, log `/tmp/principal-byot-probe.log`: **1 passed in 0.69s**. Executed from the worktree using `PYTHONPATH="$PWD" .venv/bin/python -m pytest /tmp/test_principal_byot_probe.py -q -s`. The probe inserts a real research_only document/chunk with PUBLISHERCONFIDENTIALPROBE, uses production retrieval and evidence handler, then captures and aborts immediately at dispatch_talk_to_book_byot. It proves the owner dispatch request contains the raw probe, not an actual provider delivery.

1. `interfaces/research/api/app.py:2512–2535`: authenticated investigation request model_choice is validated as UserModelChoice, then copied to every PAID_LOOP_ONE_ROLES entry, including evidence_retriever. `:2600` records owner_model_choices in the start event.
2. `orchestration/loop_one/orchestrator.py:1978–2017`: detached investigation task parses these choices and installs ResearchOwnerManifest. The context carries owner identity/model choice independently of content rights.
3. `orchestration/loop_one/orchestrator.py:715–746`: server ANTIEK_RESEARCH_POLICY_TAG selects private_research; Phase 2 retrieves chunks/subgraph then emits EvidenceRetrieveRequestedPayload with raw context. It does not reject an owner-model manifest.
4. `orchestration/loop_one/orchestrator.py:228–306,458–471`: canonical search admits research_only for private_research and renders raw chunk_text. The async wrapper uses asyncio.to_thread.
5. `orchestration/loop_one/coordinator.py:62–101`: broadcast_emit persists the event and passes its full original payload to broadcaster.broadcast.
6. `interfaces/research/api/broadcast.py:206`: asyncio.create_task schedules the evidence handler with inherited ContextVars. The experiment confirms inheritance.
7. `interfaces/research/api/evidence_retriever.py:338–354`: renders req.chunks_block directly into provider prompt and runs dispatch/parser via asyncio.to_thread. That thread also inherits the manifest (experiment confirms).
8. `interfaces/research/api/evidence_retriever.py:177–189`: first dispatch calls dispatch_loop_one. `research_owner_dispatch.py:242–269` reads inherited manifest and passes unmodified prompt plus owner/model choice to dispatch_talk_to_book_byot.
9. `owner_byot_dispatch.py:263–330` freezes OwnerCredentialBinding and OwnerByotPayer; `:208–213` calls the regular router with the raw prompt and exact owner configuration. There is no content-rights permission check here. Credential ownership/launch identity controls payment and route validity, not whether that recipient may receive source text.

Important limitation: `_budget_and_exact_config` at owner_byot_dispatch.py:335–350 refuses custom noncatalog endpoints. This is not proof an arbitrary attacker URL is accepted. It is proof an owner-account route at a permitted catalog provider receives this prompt if its ordinary credential/budget authority checks succeed. Settings resolve_owner_model_authority at settings_models_admin.py:688–720 explicitly binds the credential and provider registration to that owner.

## Regression proposal

Promote the temporary probe into tests/test_research_only_principals.py; keep real DuckDB retrieval, production EventBroadcaster, production evidence handler and production dispatch_loop_one. Spy at owner BYOT boundary, abort before outbound call. After the fix, assert raw marker never reaches that boundary (ideally assert no owner dispatch occurs after agent-only retrieval refusal). Add a positive control that authorized platform-agent derivation still retrieves the raw marker. Also cover launch-level model_choice -> manifest installation rather than only installing the real manifest directly as this bounded reproducer does. Existing tests/test_start_research_owner_dispatch.py verifies roles/operation identity but never combines owner manifest, real corpus retrieval, task inheritance, and restricted prompt.

Permission should follow source-use principal plus receiving execution account, independently of payer. A private_research string is not sufficient when the context selects an owner credential. Reject the incompatible execution principal before retrieval/dispatch; do not rely only on output masking.

## Additional reader inventory (bounded, not exhaustive)

- roles/note_taker/replay.py:173–211: `_document_excerpts_for_prompt` reads any document's first eight chunks without content_class filtering. At :478–495 they enter a durable request prompt; dispatcher called through :580–583. The same prompt includes `_render_event` :214–223, which serializes payloads wholesale. This is another raw-context consumer; owner-controlled downstream routing has not been proved in this audit.
- processing/extraction/extract.py:301–316: `_read_chunk` fetches unrestricted chunk text; :377–390 includes it in direct parameter_extractor dispatch. No dispatch_loop_one manifest route here. Internal ingestion use may be authorized, but no explicit source-use principal accompanies this read.
- orchestration/loop_one/orchestrator.py:1008: groundedness resolver reads cited chunks; evaluated through phase-6 backend. Parent is auditing substrate resolver policy.
- orchestration/loop_one/orchestrator.py:1581–1588: DRW SessionEvidencePack text is copied into derived evidence answer/supporting_claims. Whether pack entries contain source verbatim is a separate upstream contract to audit.
- orchestration/monitoring/monitor.py:445–480: raw_text is read and returned as FeedItem.body, but SQL explicitly limits class to personal_reading, so research_only is excluded there.
