from __future__ import annotations

from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from substrate.midnight_oil.private_provider_dispatch import PreparedOwnerPrivateDispatchV1


class PrivateTransportResponseFixture(BaseModel):
    model_config = ConfigDict(
        extra="forbid", strict=True, frozen=True, hide_input_in_errors=True
    )

    provider_id: str = Field(min_length=1, max_length=128)
    model_id: str = Field(min_length=1, max_length=256)
    route_key: str = Field(min_length=3, max_length=385)
    finish_reason: Literal["stop"] = "stop"
    output_text: str = Field(min_length=1, max_length=10_000_000)
    route_index: Literal[0] = 0
    retry_index: Literal[0] = 0
    fallback_index: Literal[0] = 0

    @model_validator(mode="after")
    def _bounded_output(self) -> PrivateTransportResponseFixture:
        if len(self.output_text.encode("utf-8")) > 10_000_000:
            raise ValueError("test-only private response exceeds its byte bound")
        return self


def invoke_test_transport_once(
    prepared: PreparedOwnerPrivateDispatchV1,
    transport: Callable[
        [bytes], PrivateTransportResponseFixture | dict[str, object]
    ],
) -> PrivateTransportResponseFixture:
    """Exercise one spy call; production code intentionally has no equivalent."""
    try:
        prepared = PreparedOwnerPrivateDispatchV1.model_validate(
            prepared.model_dump(mode="python")
        )
    except (TypeError, ValueError):
        raise ValueError("test-only private dispatch envelope is invalid") from None
    raw = transport(prepared.provider_request_bytes)
    try:
        response = PrivateTransportResponseFixture.model_validate(
            raw.model_dump(mode="python")
            if isinstance(raw, PrivateTransportResponseFixture)
            else raw
        )
    except (TypeError, ValueError):
        raise ValueError("test-only private response is invalid") from None
    descriptor = prepared.descriptor
    if (
        response.provider_id != descriptor.provider_id
        or response.model_id != descriptor.model_id
        or response.route_key != descriptor.route_key
        or len(response.output_text.encode("utf-8")) > prepared.max_output_bytes
    ):
        raise ValueError("test-only private response route conflicts")
    return response


__all__ = ["PrivateTransportResponseFixture", "invoke_test_transport_once"]
