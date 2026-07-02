## Sprint SPR-04 (ANTIEK-HPRJ) — Signed Projection Shell — Handoff

### Env Card

| Field | Value |
|-------|-------|
| Date (UTC) | 2026-06-30 |
| Repo root (`pwd`) | `/Users/slimydog/Desktop/Antiek` |
| Branch | `html-projection/land-antiek` |
| Commit SHA | `9323975739465544c50c11813daedcaef631ca0f` |
| Python | `/Users/slimydog/Desktop/Antiek/.venv/bin/python` (`Python 3.12.13`) |
| LLM contacted this session | `no` |
| Network required for gates | `no` |

### Not proved

| Row | Hermetic proof | Not proved |
|-----|----------------|------------|
| `.antiek` shell | `projection.html` entry, manifest hash, deterministic order, pre-shell compatibility | Cross-version compatibility with older external readers |
| Signature coverage | Mutated shell byte, removed shell, and mutated manifest hash all fail verification | Hardware-backed signing keys |
| Leak guard | Shell byte-grep catches structural substrate leaks before write | Full semantic review of every possible prose phrase |
| Single-file variant | Tampered markup/island fail; missing/double signature fails; disk verify works | Browser extension or OS file association UX |

### Status

`done` — `.antiek` containers now carry a signed, deterministic, script-free `projection.html` shell, and the single-file `.antiek.html` share variant verifies rendered markup plus island integrity.

### Files touched

- `services/antiek_format/native_writer.py` — schema `1.1.0`, deterministic `projection.html` entry, `projection_sha256` manifest binding, shell byte-grep for forbidden substrate-shaped leaks.
- `services/antiek_format/native_reader.py` — reads optional shell bytes, preserves pre-1.1.0 compatibility, and marks signature invalid when declared shell hash is absent or mismatched.
- `services/antiek_format/single_file.py` — deterministic `name.antiek.html` wrapper and verifier using an inert signature island over rendered HTML with the signature island excised.
- `services/antiek_format/tests/test_shell.py` — adversarial shell gates for order, determinism, version bump, backwards read, signature coverage, and leak grep.
- `services/antiek_format/tests/test_single_file.py` — single-file verification, tamper, missing signature, double-wrap, disk round-trip, and determinism gates.
- `services/html_projection/tests/test_share_parity.py` — export parity check confirming `.antiek` output carries the SPR-04 self-render shell.

### Milestones (checkboxes)

- [x] M1: Amendment shape — shell is derived, not canonical; `content.tiptap.json` remains source of truth.
- [x] M2: Container shell — `projection.html` rides after content, schema bumps to `1.1.0`, and writes remain byte-deterministic.
- [x] M3: Integrity binding — signed manifest carries `projection_sha256`; mutated or missing shell invalidates verification.
- [x] M4: Leak guard — rendered shell is checked for forbidden substrate-shaped bytes before archive write.
- [x] M5: Single-file share variant — `.antiek.html` carries a doc-model island plus detached signature island and verifies tampered markup/island failures.
- [x] M6: Export parity — routed `.antiek` artifacts expose the shell while unsigned HTML remains plain projection output.

### Gate results

| gate | command | exit |
|------|---------|------|
| SPR-04 shell + single-file focused bundle | `./.venv/bin/python -m pytest services/antiek_format/tests/test_shell.py services/antiek_format/tests/test_single_file.py services/html_projection/tests/test_share_parity.py -q` | 0 (`33 passed in 0.62s`) |

### Decisions made mid-flight

- Bound shell integrity through `projection_sha256` in the signed manifest rather than widening the Ed25519 signing input; this matches the existing audio integrity pattern.
- Treated `projection.html` as derived and disposable: readers surface bytes for display but never parse it back as canonical content.
- Signed the whole single-file rendered HTML with the signature island excised, so both island tampering and rendered-markup tampering fail verification.

### Assumptions surfaced

- The minor schema bump is additive: pre-shell `1.0.0` containers still read, and older readers can ignore the extra zip entry.
- The shell leak grep is intentionally structural. It catches substrate-shaped byte leaks without banning ordinary prose about chunks or embeddings.
- A single-file `.antiek.html` is a share artifact, not the canonical storage format; the `.antiek` zip remains the canonical signed container.

### Steelman rejected alternative

Make `projection.html` the canonical artifact and parse it back on ingest. Steelman: one file is easier to inspect and share. Why it lost: the renderer output is derived presentation; parsing it would make CSS/HTML churn affect canonical content and weaken the container’s source-of-truth boundary.

### Open questions

- External reader compatibility should be smoke-tested when a separate reader implementation exists.
- Product UX still needs to decide where `.antiek.html` appears versus zipped `.antiek` in share/export menus.

### Scope Map

**Investigation ID:** ANTIEK-HPRJ-SPR-04

**Next sprint:** SPR-05 synthesis artifact export.

### Out-of-scope temptations encountered

- Wanted to make the shell executable for richer offline behavior; resisted because HPRJ projection artifacts must remain script-free.
- Wanted to use screenshots as the primary shell proof; resisted because byte determinism, hash binding, and tamper tests are the load-bearing contract.
