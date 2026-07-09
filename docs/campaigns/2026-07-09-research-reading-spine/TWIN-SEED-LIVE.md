# Twin seed live note_taker (residual bz)

## Default (safe)

- Offline insight + question stubs via `seed_twins_for_asset`
- No LLM / network calls

## Enabling live seed (operator-gated)

Both required:

1. Env: `ANTIEK_TWIN_SEED_LIVE=1`
2. Process inject: `configure_twin_seed_live(fn)` where  
   `fn(title, body_text) -> Sequence[tuple[kind, text]]`  
   and `kind` is `"insight"` or `"question"`

```python
from substrate.engagement_spine import configure_twin_seed_live

def note_taker(title: str, body: str):
    # call roles.note_taker / dispatch; return pairs
    return [("insight", "..."), ("question", "...")]

configure_twin_seed_live(note_taker)
```

## Honesty fields on payload

- `live_seed: bool`
- `seed_source: ...offline | ...live`
- `force_offline=True` always uses stubs

## Related

- Hydrate default seeds twins (`seed_twins=True`)
- Marketplace host seeds twins into engagement store
- Hosted book windows mount TwinNotesPanel + ResearchContextPanel
