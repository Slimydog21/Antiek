"""OpenAI Chat Completions ↔ TileRT GLM5Generator bridge.

Antiek dispatch sends a single user message today; this module accepts
full ``messages[]`` for forward compatibility (Codex, tools later).
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from typing import Any


def _approx_tokens(text: str) -> int:
    # Dispatch cost reports need stable, monotonic usage — not tokenizer-exact.
    return max(1, len(text) // 4)


def messages_to_prompt(messages: list[dict[str, Any]]) -> str:
    """Flatten chat messages into one generation prompt."""
    parts: list[str] = []
    for msg in messages:
        role = (msg.get("role") or "user").strip().lower()
        content = msg.get("content")
        if content is None:
            continue
        if isinstance(content, list):
            # Multimodal: keep text blocks only for v1
            texts = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    texts.append(str(block.get("text", "")))
            content = "\n".join(texts)
        text = str(content).strip()
        if not text:
            continue
        if role == "system":
            parts.append(f"[system]\n{text}")
        elif role == "assistant":
            parts.append(f"[assistant]\n{text}")
        else:
            parts.append(text)
    if not parts:
        raise ValueError("messages contained no usable text")
    return "\n\n".join(parts)


def build_chat_completion(
    *,
    model: str,
    prompt: str,
    completion: str,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
) -> dict[str, Any]:
    pt = prompt_tokens if prompt_tokens is not None else _approx_tokens(prompt)
    ct = completion_tokens if completion_tokens is not None else _approx_tokens(completion)
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": completion},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": pt,
            "completion_tokens": ct,
            "total_tokens": pt + ct,
        },
    }


def handle_chat_completions(
    body: dict[str, Any],
    *,
    generate: Callable[[str, int], str],
    default_model: str = "glm5",
) -> dict[str, Any]:
    messages = body.get("messages")
    if not isinstance(messages, list) or not messages:
        raise ValueError("messages must be a non-empty array")
    model = str(body.get("model") or default_model)
    max_tokens = int(body.get("max_tokens") or 4096)
    max_tokens = max(1, min(max_tokens, 32768))
    prompt = messages_to_prompt(messages)
    completion = generate(prompt, max_tokens)
    return build_chat_completion(model=model, prompt=prompt, completion=completion)