# compounding/domain_skills/

Pointers and adapters for the four domain skills.

The actual skill files live at:

```
~/.hermes/skills/research/quantum-knowledge/
~/.hermes/skills/research/defense-knowledge/
~/.hermes/skills/research/ai-infrastructure-knowledge/
~/.hermes/skills/research/semiconductor-knowledge/
```

This directory provides:

- A loader that reads each skill into a structured representation.
- A diff utility used by `compounding/verification/`.
- A snapshot utility for capturing pre-Phase-8 state.

## Discipline

This module is the only code path that reads/writes the domain skill
files. Any other code that needs domain-skill content goes through
this module's API so the access patterns are auditable.
