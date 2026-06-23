# Codex / mimo2codex → TileRT GLM-5 (ATSB SPR-06 M1)

Personal validation only. Production Antiek routing uses gateway `ANTIEK_TILERT_*`
on the VM; see README §5.

**Prerequisite:** OA-022 complete (`./scripts/tilert_modal_preflight.sh` exit 0).

## Env

```bash
export ANTIEK_TILERT_BASE_URL="https://<modal-web-host>"   # no trailing slash
export ANTIEK_TILERT_API_KEY="<ANTIEK_TILERT_MODAL_TOKEN>"
```

## OpenAI-compat contract

- Base: `$ANTIEK_TILERT_BASE_URL/v1`
- Auth: `Authorization: Bearer $ANTIEK_TILERT_API_KEY`
- Model id: **`glm5`** (alias `glm-5.2` may appear in `/v1/models`)

## mimo2codex

Point the generic upstream provider at the base URL above with the same Bearer
token and model `glm5`. Record one completion (latency + model id) in operator
notes when validating TPOT.

## Codex CLI

Mirror the same URL/key in a dedicated profile (e.g. extend an existing Modal GLM
profile) — do not commit secrets. This path proves TileRT latency for the
operator; it does not prove DRW synthesizer verifier rates (SPR-07).