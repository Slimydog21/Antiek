"""Explicit hermetic pricing/signing authority for launch-route tests only."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any


def configure_research_quote_authority(monkeypatch: Any, root: str | Path) -> None:
    import interfaces.research.api.settings_budget as settings_budget

    path = Path(root) / "dispatch-quote-test.yaml"
    path.write_text(
        """
role_tiers:
  decomposer: pro
  evidence_retriever: pro
  parameter_extractor: pro
  connector: pro
  synthesizer: pro
  knowledge_extractor: pro
tier_defaults:
  pro:
    max_tokens: 100
    temperature: 0.2
    context_budget_tokens: 1000
tiers:
  pro:
    provider: provider-test
    model: model-test
    pricing:
      input_per_mtok: 1.0
      output_per_mtok: 2.0
      cached_input_per_mtok: 0.1
      currency: USD
      billing_unit: per_million_tokens
      source_url: https://provider.example/pricing
      verified_at: '2026-01-01T00:00:00Z'
      expires_at: '2099-01-01T00:00:00Z'
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setattr(settings_budget, "_dispatch_config_path", lambda: path)
    key = b"antiek-research-quote-test-key!!"
    encoded = base64.urlsafe_b64encode(key).rstrip(b"=").decode("ascii")
    monkeypatch.setenv(
        "ANTIEK_RESEARCH_QUOTE_KEYRING_JSON",
        json.dumps(
            {
                "schema_version": 1,
                "active_key_id": "test-current",
                "keys": {"test-current": encoded},
            }
        ),
    )


def post_signed_investigation(client: Any, payload: dict[str, Any]) -> Any:
    quote = client.post("/investigations/quote", json=payload)
    assert quote.status_code == 200, quote.text
    token = quote.json()["quote_token"]
    return client.post(
        "/investigations",
        json={**payload, "research_quote_token": token},
    )


def signed_reserved_body(
    client: Any,
    parent_investigation_id: str,
    question_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    base = (
        f"/research/{parent_investigation_id}/questions/{question_id}"
        "/reserved-launch"
    )
    quote = client.post(f"{base}/quote", json=payload)
    assert quote.status_code == 200, quote.text
    return {**payload, "research_quote_token": quote.json()["quote_token"]}


async def async_signed_body(
    client: Any,
    quote_path: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    quote = await client.post(quote_path, json=payload)
    assert quote.status_code == 200, quote.text
    return {**payload, "research_quote_token": quote.json()["quote_token"]}
