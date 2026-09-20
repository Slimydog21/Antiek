"""BYOK (bring-your-own-key) credential store + X ingestion pipelines.

Personal-Reading Lane SPR-08. The operator supplies their OWN X / Twitter API key
(BYOK) — the load-bearing legal move that makes the fetch an AUTHORIZED source
under X's developer agreement (a scrape or a single shared key would be a
Terms-of-Service breach). This package:

  * stores that key ENCRYPTED AT REST and decrypts it only in-process behind a
    redacting :class:`SecretStr` (``store.py`` + ``secret_str.py``, M1);
  * lets the operator register per-account ingestion pipelines (``pipelines.py``,
    M2) — data-only config, no daemon / no scheduler (§16 box-bounded);
  * runs a pipeline → maps an X API v2 payload through the EXISTING
    ``acquisition/twitter`` adapter into ``content_class='personal_reading'`` via
    the single box-bounded writer (``runner.py`` + ``acquisition/twitter/
    api_client.py``, M3).

X content lands ``personal_reading``: owner-readable, NEVER served publicly,
NEVER ad-attributed, and NEVER trained on — the last honoring X's no-training
clause (pinned by ``tests/test_x_byok_training_exclusion.py``, M4, which reuses
SPR-01's ``substrate.constants.NON_TRAINABLE_CONTENT_CLASSES`` denylist).
"""

from runtime.byok.secret_str import SecretStr
from runtime.byok.store import (
    CredentialIntegrityError,
    CredentialMetadata,
    list_credentials,
    load_credential,
    store_credential,
)

__all__ = [
    "SecretStr",
    "CredentialMetadata",
    "CredentialIntegrityError",
    "store_credential",
    "load_credential",
    "list_credentials",
]
