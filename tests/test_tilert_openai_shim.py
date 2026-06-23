from __future__ import annotations

import os
import sys

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_SHIM = os.path.join(_REPO, "infrastructure", "modal", "tilert_glm5")
if _SHIM not in sys.path:
    sys.path.insert(0, _SHIM)

from openai_shim import handle_chat_completions, messages_to_prompt  # noqa: E402


def test_messages_to_prompt_flattens_roles():
    prompt = messages_to_prompt(
        [
            {"role": "system", "content": "Be terse."},
            {"role": "user", "content": "Hello"},
        ]
    )
    assert "[system]" in prompt
    assert "Hello" in prompt


def test_handle_chat_completions_shape():
    out = handle_chat_completions(
        {"model": "glm5", "max_tokens": 32, "messages": [{"role": "user", "content": "Hi"}]},
        generate=lambda _p, _m: "Hello there.",
        default_model="glm5",
    )
    assert out["choices"][0]["message"]["content"] == "Hello there."
    assert out["usage"]["total_tokens"] > 0