"""Provider-fault injector: a registered provider's .call raises the real
ProviderError (503 / timeout); restored on teardown; deterministic."""

from __future__ import annotations

import pytest

from tools.faultinject import arm, provider_fault


class _StubProvider:
    """Minimal structural Provider for the router registry. Its real .call
    returns a sentinel so the disarmed path is observable."""

    name = "stub"

    def call(self, *, model, prompt, max_tokens, temperature):
        return {"ok": True, "model": model}

    def normalize_usage(self, raw_usage):  # pragma: no cover - not exercised
        from substrate.dispatch.base import NormalizedUsage

        return NormalizedUsage(input_tokens=0, output_tokens=0)


_CALL_KWARGS = dict(model="m", prompt="p", max_tokens=8, temperature=0.0)


@pytest.fixture
def stub_registered():
    from substrate.dispatch.router import (
        register_provider,
        reset_provider_registry,
    )

    reset_provider_registry()
    register_provider(_StubProvider())
    try:
        yield
    finally:
        reset_provider_registry()


def test_503_raises_provider_error(stub_registered):
    from substrate.dispatch.base import ProviderError
    from substrate.dispatch.router import get_provider

    with provider_fault(kind="503", provider="stub"):
        with pytest.raises(ProviderError) as ei:
            get_provider("stub").call(**_CALL_KWARGS)
        assert "503" in str(ei.value)
        assert ei.value.provider == "stub"
    # Disarmed: the real call returns the sentinel.
    assert get_provider("stub").call(**_CALL_KWARGS) == {"ok": True, "model": "m"}


def test_timeout_kind_raises_provider_error(stub_registered):
    from substrate.dispatch.base import ProviderError
    from substrate.dispatch.router import get_provider

    with provider_fault(kind="timeout", provider="stub"):
        with pytest.raises(ProviderError) as ei:
            get_provider("stub").call(**_CALL_KWARGS)
        assert "timeout" in str(ei.value).lower()


def test_invalid_kind_rejected(stub_registered):
    with pytest.raises(ValueError):
        with provider_fault(kind="418", provider="stub"):
            pass


def test_unregistered_provider_surfaces_loudly():
    from substrate.dispatch.router import reset_provider_registry

    reset_provider_registry()
    with pytest.raises(KeyError):
        with provider_fault(kind="503", provider="does-not-exist"):
            pass


def test_fail_on_call_survives_first_fails_second(stub_registered):
    from substrate.dispatch.base import ProviderError
    from substrate.dispatch.router import get_provider

    with provider_fault(kind="503", provider="stub", fail_on_call=2):
        assert get_provider("stub").call(**_CALL_KWARGS) == {"ok": True, "model": "m"}
        with pytest.raises(ProviderError):
            get_provider("stub").call(**_CALL_KWARGS)


def test_call_restored_after_block(stub_registered):
    from substrate.dispatch.router import get_provider

    with provider_fault(kind="503", provider="stub"):
        pass
    # The original bound method is back (no leaked instance attribute).
    prov = get_provider("stub")
    assert "call" not in vars(prov)
    assert prov.call(**_CALL_KWARGS) == {"ok": True, "model": "m"}


def test_call_restored_even_when_body_raises(stub_registered):
    from substrate.dispatch.router import get_provider

    class Boom(RuntimeError):
        pass

    with pytest.raises(Boom):
        with provider_fault(kind="503", provider="stub"):
            raise Boom()
    assert get_provider("stub").call(**_CALL_KWARGS) == {"ok": True, "model": "m"}


def test_arm_generic_entry_point(stub_registered):
    from substrate.dispatch.base import ProviderError
    from substrate.dispatch.router import get_provider

    with arm("provider_fault", kind="503", provider="stub"):
        with pytest.raises(ProviderError):
            get_provider("stub").call(**_CALL_KWARGS)


def test_double_arm_same_provider_refused(stub_registered):
    from substrate.dispatch.router import get_provider

    with provider_fault(kind="503", provider="stub"):
        with pytest.raises(RuntimeError):
            with provider_fault(kind="timeout", provider="stub"):
                pass
    # Outer restored cleanly and the guard was released.
    assert get_provider("stub").call(**_CALL_KWARGS) == {"ok": True, "model": "m"}
