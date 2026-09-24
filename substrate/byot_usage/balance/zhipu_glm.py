"""Z.ai/GLM native-balance capability.

The published Z.ai API inventory has no balance endpoint or response schema.
USD model pricing does not establish the unit of an account balance. Do not
send a credential to the former guessed ``/user/balance`` path.

Sources: https://docs.z.ai/api-reference/introduction
         https://docs.z.ai/llms.txt
"""

from __future__ import annotations

from runtime.byok.secret_str import SecretStr

from .base import BalanceSnapshot


def fetch_zhipu_glm_balance(
    key: SecretStr,
    *,
    base_url: str,
    http: object,
) -> BalanceSnapshot:
    """Report the missing provider balance contract without making a request."""
    del key, base_url, http
    return BalanceSnapshot(
        catalog_id="zhipu_glm",
        kind="unavailable",
        note="Provider has not documented a native balance API.",
    )
