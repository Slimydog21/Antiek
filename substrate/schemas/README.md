# substrate/schemas/

Pydantic schemas for events, nodes, edges, chunks, syntheses, source
attributions, skill versions, and dispatch payloads.

## Files (planned)

- `events.py` — The typed event envelope: `event_id`, `timestamp`,
  `investigation_id`, `phase`, `role`, `action_type`, `payload`,
  `parent_event_id`, `parameter_version`.
- `actions.py` — The enumerated action vocabulary plus the payload
  schema per action type. The minimum stable set is documented in
  `architecture_notes.md` §2.1.
- `graph.py` — Node and edge schemas. Typed nodes (claim, person,
  organization, paper, interview, theme, hardware, …). Typed edges
  with source attribution.
- `attribution.py` — Source-to-output citation tracking. Distinguishes
  public-source attribution from primary-interview attribution
  (consent, contribution, citation rights).
- `synthesis.py` — Archived-synthesis schema, including the full
  skill-version triple and `ANTIEK_PARAM_VERSION` stamp.
- `dispatch.py` — Context-pack and response schemas.

## Discipline

These schemas are the eventual training-data format. Underspecified
schemas now produce uncurated event logs later, which produce bad
training data, which produce bad models.

Schema changes are versioned and require migration paths for prior
events. See architecture_notes §7.
