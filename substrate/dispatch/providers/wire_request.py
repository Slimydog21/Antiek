"""Provider-built request data; callers must establish send authority separately."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class BuiltProviderRequest:
    """A request description, with private headers and body excluded from repr.

    ``model`` retains the adapter input used for response/error labels before
    body overrides. It is not evidence of the model that served a response.
    The dictionaries remain ordinary builder data, not an admitted policy.
    """

    url: str = field(repr=False)
    headers: dict[str, str] = field(repr=False)
    body: dict[str, Any] = field(repr=False)
    model: str = field(repr=False)
