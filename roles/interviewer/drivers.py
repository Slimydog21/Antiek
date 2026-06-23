"""Driver identification for the brainstorm-interview (specs/write/ SPR-05 M2).

The operator dumps a raw idea; the agent identifies the **insights,
questions, and data** driving it, then asks clarifying questions. This
module is the structured-output half: it parses the agent's
driver-identification response into a typed ``DriverSet`` and supplies the
prompt fragment.

It is a net-new sibling to the interviewer's turn-taking parser (which the
Speak workflow also uses) so the brainstorm extension does not perturb
that shared file. The clarifying-question loop itself reuses the existing
``InterviewerResult`` (``must_cover_remaining_indices`` /
``follow_up_for_prior_turn``); only the driver extraction is new.

Honesty rule (rigor #1): "data" the user *asserts* in a brainstorm is a
**claim to verify**, not established data. The parser keeps data points
separate from insights so ``substrate/write/brainstorm_blocks`` can flag
them unverified rather than minting them as fact.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .._json_decode import extract_json_object


class DriverValidationError(ValueError):
    """Raised when the driver-identification output fails validation."""


@dataclass(frozen=True)
class DriverSet:
    """The insights, questions, and data points driving a dumped idea.

    - ``insights``: assertions/observations the idea rests on.
    - ``questions``: open questions the idea raises or depends on.
    - ``data_points``: quantitative/factual claims the user asserted —
      treated as claims to verify, NOT established data.
    """

    insights: list[str] = field(default_factory=list)
    questions: list[str] = field(default_factory=list)
    data_points: list[str] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not (self.insights or self.questions or self.data_points)


DRIVER_IDENTIFICATION_PROMPT = """\
The writer just dumped a raw idea. Identify, in the background, the
distinct units of meaning driving it. Separate them into three kinds:

- insights: assertions or observations the idea rests on
- questions: open questions the idea raises or depends on
- data_points: specific quantitative or factual claims the writer
  asserted (these are CLAIMS TO VERIFY, not established facts)

Do not invent material the writer did not imply. If a kind is empty,
return an empty list for it. Return JSON only:

```json
{"insights": ["..."], "questions": ["..."], "data_points": ["..."]}
```
"""


def _string_list(data: dict, key: str) -> list[str]:
    raw = data.get(key) or []
    if not isinstance(raw, list):
        raise DriverValidationError(f"{key} must be a list, got {type(raw).__name__}")
    out: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            raise DriverValidationError(f"{key} entries must be strings, got {item!r}")
        s = item.strip()
        if s:
            out.append(s)
    return out


def parse_drivers(raw: str) -> DriverSet:
    """Parse + validate a driver-identification response into a DriverSet."""
    data = extract_json_object(raw)
    if data is None:
        raise DriverValidationError("no JSON object in driver-identification response")
    return DriverSet(
        insights=_string_list(data, "insights"),
        questions=_string_list(data, "questions"),
        data_points=_string_list(data, "data_points"),
    )
