"""Ingestion boundary (HPRJ SPR-07).

Artifacts are DATA, never instructions. When a born-Antiek artifact (a
``.antiek`` container or a single-file ``name.antiek.html``) returns to Antiek,
ingestion reads ONLY its signed structured doc-model — never the rendered HTML
— and a tampered signature quarantines rather than silently ingesting. The
structured payload is framed as quoted data on its way into any LLM context.
"""
