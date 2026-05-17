# interfaces/reading/

Consumption-side PDF reading interface. **Scaffolded, not implemented
in this build.**

## What this would be

A reading surface where the operator can:

- Open an ingested PDF
- Highlight a paragraph to query
- Get a streaming mini-briefer in a pop-up that pulls from the graph
  and the skill layer

## Why deferred

This is real frontend engineering — PDF.js or MuPDF integration,
contextual selection capture, streaming dialogue overlay. 8–12 weeks of
focused work that shouldn't be conflated with substrate consolidation.
See architecture_notes §5.

## What's here now

Empty package marker plus this README. Stub components and the
documented data flow get added when this interface enters its build
window.
