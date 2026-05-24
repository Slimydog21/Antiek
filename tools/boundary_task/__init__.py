"""
``python -m tools.boundary_task`` — operator-facing boundary-task queue.

Hashimoto's discipline: at every session boundary (start-of-day,
before driving, end-of-day), ask "what's a slow thing my agent
could do for the next ~30 minutes?" and queue it. The §7
continuous-research daemon (when wired) reads from this queue first;
the operator pulls progress via ``status`` rather than waiting for
push notifications.

Storage: a single-writer DuckDB file at ``~/.antiek/boundary_queue.db``.
Goes through ``runtime.db_lock.connect_write`` so the queue
participates in the I-001 single-writer invariant.

Subcommands: see ``__main__.py``.
Spec: ~/specs/antiek-hashimoto-engineering/sprint-e5-boundary-cli.html
"""
