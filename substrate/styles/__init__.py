"""Per-user forked-style persistence for the style wheel (spec §5.5, S2).

Only user forks are stored here; the built-in wheel lives in code
(``services/html_projection/styles.py``) and is always layered UNDER the
stored forks when a request assembles a user's wheel. See
``substrate/styles/store.py`` for the store itself.
"""

from .store import UserStyleStore

__all__ = ["UserStyleStore"]
