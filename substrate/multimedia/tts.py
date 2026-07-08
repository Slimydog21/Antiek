"""TTS provider seam (multimedia SPR-04, milestone 2).

A mockable text-to-speech interface so audio assembly can run in CI against FAKE
audio bytes with deterministic durations, while a real provider call stays
operator-gated behind an environment variable. This keeps the multimedia lane
credential-free in CI (matching sprints 01-03) while leaving the real-render
switch as a single, auditable flip.

Design invariants:

* DETERMINISTIC FAKE OUTPUT. :class:`FakeTTSProvider` derives audio bytes and a
  duration purely from the input text + voice + speed, so the same paragraph
  always yields the same ``sha256`` and the same duration. This is what lets the
  audio manifest's integrity hashes be asserted in CI without a real voice.
* COST IS ESTIMATED, NEVER FABRICATED. ``estimate_cost`` returns a modeled USD
  figure from characters + a per-character rate; real providers override it with
  their metered rate. No cost row is ever invented from nothing.
* THE SEAM IS THE UNIT OF REPLACEABILITY. A real adapter (OpenAI
  ``gpt-4o-mini-tts``, already the platform ``tts`` dispatch tier) implements the
  same :class:`TTSProvider` protocol and is selected by ``make_tts_provider``,
  which returns the fake unless the operator sets ``ANTIEK_TTS_PROVIDER=openai``
  (and a key). Callers never branch on provider identity.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass

# A conservative adult-narration speech rate (characters/second at speed=1.0).
# Used by the fake provider so chapter durations are plausible, not so they match
# any real voice. Real providers return their OWN metered duration.
_DEFAULT_CHARS_PER_SECOND = 15.0

# Modeled per-character cost placeholders (USD). Operator owns the real rates;
# these exist so a cost ROW is structurally present, never to report spend.
_FAKE_COST_PER_CHAR_USD = 0.0


@dataclass(frozen=True)
class TTSRequest:
    """One synthesis unit: speak ``text`` in ``voice`` at ``speed``.

    ``speed`` is a multiplier on the base rate (1.0 = normal, 1.5 = 1.5x). Values
    are clamped by the provider so a runaway caller can't request 100x and get a
    zero-duration (division) file."""

    text: str
    voice: str = "narrator"
    speed: float = 1.0

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("TTS request text must be non-empty")
        if self.speed <= 0:
            raise ValueError(f"TTS speed must be > 0, got {self.speed}")
        if not self.voice.strip():
            raise ValueError("TTS voice must be non-empty")


@dataclass(frozen=True)
class TTSResult:
    """Synthesized audio for one request, with provenance + cost.

    ``audio_bytes`` is the raw payload (fake = deterministic digest; real =
    provider bytes). ``duration_seconds`` is what the assembly layer timestamps
    against. ``cost_usd`` is the modeled spend for this unit."""

    audio_bytes: bytes
    mime: str
    duration_seconds: float
    cost_usd: float
    provider: str
    voice: str
    speed: float

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.audio_bytes).hexdigest()


class TTSProvider:
    """The replaceable TTS seam. Subclasses implement :meth:`synthesize`.

    ``estimate_cost`` is the modeled USD for a request; the default models from
    characters, real providers override with metered rates. ``characters_per_second``
    lets the fake provider produce plausible durations and lets a real provider
    advertise its base rate for budgeting."""

    name: str = "tts"
    characters_per_second: float = _DEFAULT_CHARS_PER_SECOND

    def estimate_cost(self, request: TTSRequest) -> float:
        """Modeled USD for one request. Default: characters * per-char rate.

        The base per-character rate is zero so a cost ROW is structurally present
        (the manifest requires one) without ever fabricating spend; a real
        provider overrides this with its metered rate."""
        return round(len(request.text) * _FAKE_COST_PER_CHAR_USD, 6)

    def synthesize(self, request: TTSRequest) -> TTSResult:  # pragma: no cover - abstract
        raise NotImplementedError(
            f"{type(self).__name__} must implement synthesize(); a TTS seam with no "
            "synthesis path cannot produce audio"
        )


class FakeTTSProvider(TTSProvider):
    """Deterministic, credential-free TTS for CI + offline development.

    Audio bytes are a fixed schema header + a SHA-256 digest of (voice, speed,
    text), so identical input yields byte-identical output -> stable manifest
    hashes. Duration is ``len(text) / (chars_per_second * speed)``: deterministic,
    plausible, and speed-aware. Cost is always the modeled estimate (zero by
    default). No network, no key, no nondeterminism."""

    name = "fake"
    mime = "audio/fake-pcm"

    def synthesize(self, request: TTSRequest) -> TTSResult:
        speed = max(min(request.speed, 4.0), 0.25)  # clamp to a sane narratable range
        digest = hashlib.sha256(
            f"{request.voice}\x00{speed}\x00{request.text}".encode()
        ).digest()
        # A small fixed schema prefix so fake audio is self-identifying and never
        # empty (zero-length payloads would collapse distinct paragraphs).
        audio = b"ANTIEK-FAKE-TTS\x00" + digest
        effective_cps = self.characters_per_second * speed
        duration = round(len(request.text) / max(effective_cps, 0.1), 3)
        return TTSResult(
            audio_bytes=audio,
            mime=self.mime,
            duration_seconds=duration,
            cost_usd=self.estimate_cost(request),
            provider=self.name,
            voice=request.voice,
            speed=speed,
        )


# ---------------------------------------------------------------------------
# Provider selection — the single operator-gated switch.
# ---------------------------------------------------------------------------

_PROVIDER_FACTORIES: dict[str, type[TTSProvider]] = {
    "fake": FakeTTSProvider,
}


def make_tts_provider(*, provider: str | None = None) -> TTSProvider:
    """Return a TTS provider. Defaults to the credential-free fake.

    A real provider is opt-in via ``ANTIEK_TTS_PROVIDER`` (e.g. ``"openai"``) AND
    its key env var. Until a real adapter is registered AND the operator opts in,
    this returns the fake — so CI and offline dev never need a key, and a real
    voice is a single auditable flip, not a code change at every call site."""
    chosen = provider or os.environ.get("ANTIEK_TTS_PROVIDER") or "fake"
    factory = _PROVIDER_FACTORIES.get(chosen)
    if factory is None:
        # Unknown provider -> fail closed to the fake, never to a real-adapter
        # import that could surprise CI. The operator flips explicitly.
        return FakeTTSProvider()
    return factory()
