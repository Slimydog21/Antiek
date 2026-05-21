"""Partner-substrate identity tests (Sprint 30+ thread 1)."""

from __future__ import annotations

import pytest

from substrate.cross_graph.partner_identity import (
    DEFAULT_CLOCK_SKEW_SECONDS,
    DEFAULT_TOKEN_TTL_SECONDS,
    PartnerIdentityError,
    PartnerRegistry,
    PartnerTrustState,
    generate_partner_token,
    generate_shared_secret,
    is_partner_trusted,
    register_partner,
    revoke_partner,
    trust_partner,
    verify_partner_token,
)


# ── Registry state machine ─────────────────────────────────────────


def test_register_partner_lands_in_pending_handshake():
    reg = PartnerRegistry()
    secret = generate_shared_secret()
    rec = register_partner(
        reg,
        display_name="Partner Lab",
        substrate_url="https://partner.example.com",
        shared_secret_hex=secret,
    )
    assert rec.state is PartnerTrustState.PENDING_HANDSHAKE
    assert rec.shared_secret_hex == secret
    assert is_partner_trusted(reg, rec.partner_id) is False


def test_duplicate_partner_id_refused():
    reg = PartnerRegistry()
    secret = generate_shared_secret()
    register_partner(
        reg, display_name="A", substrate_url="https://a", shared_secret_hex=secret,
        partner_id="prt-fixed",
    )
    with pytest.raises(PartnerIdentityError):
        register_partner(
            reg, display_name="B", substrate_url="https://b", shared_secret_hex=secret,
            partner_id="prt-fixed",
        )


def test_trust_promotion():
    reg = PartnerRegistry()
    rec = register_partner(
        reg, display_name="P", substrate_url="https://p",
        shared_secret_hex=generate_shared_secret(),
    )
    trusted = trust_partner(reg, partner_id=rec.partner_id, operator_notes="handshake verified")
    assert trusted.state is PartnerTrustState.TRUSTED
    assert "handshake verified" in trusted.operator_notes
    assert is_partner_trusted(reg, rec.partner_id) is True


def test_trust_only_from_pending_handshake():
    reg = PartnerRegistry()
    rec = register_partner(
        reg, display_name="P", substrate_url="https://p",
        shared_secret_hex=generate_shared_secret(),
    )
    trust_partner(reg, partner_id=rec.partner_id)
    # Second trust call refused.
    with pytest.raises(PartnerIdentityError):
        trust_partner(reg, partner_id=rec.partner_id)


def test_revoke_terminal():
    reg = PartnerRegistry()
    rec = register_partner(
        reg, display_name="P", substrate_url="https://p",
        shared_secret_hex=generate_shared_secret(),
    )
    trust_partner(reg, partner_id=rec.partner_id)
    revoke_partner(reg, partner_id=rec.partner_id, revocation_reason="leak")
    assert is_partner_trusted(reg, rec.partner_id) is False
    # Re-revoke refused.
    with pytest.raises(PartnerIdentityError) as ei:
        revoke_partner(reg, partner_id=rec.partner_id, revocation_reason="leak again")
    assert "already REVOKED" in str(ei.value)


def test_unknown_partner_id_raises():
    reg = PartnerRegistry()
    with pytest.raises(PartnerIdentityError):
        trust_partner(reg, partner_id="nope")
    with pytest.raises(PartnerIdentityError):
        revoke_partner(reg, partner_id="nope", revocation_reason="x")


def test_all_trusted_deterministic_ordering():
    reg = PartnerRegistry()
    for pid in ("prt-z", "prt-a", "prt-m"):
        register_partner(
            reg, display_name=pid, substrate_url=f"https://{pid}",
            shared_secret_hex=generate_shared_secret(),
            partner_id=pid,
        )
        trust_partner(reg, partner_id=pid)
    assert [p.partner_id for p in reg.all_trusted()] == ["prt-a", "prt-m", "prt-z"]


def test_revoked_partner_not_in_all_trusted():
    reg = PartnerRegistry()
    register_partner(
        reg, display_name="a", substrate_url="https://a",
        shared_secret_hex=generate_shared_secret(), partner_id="prt-a",
    )
    trust_partner(reg, partner_id="prt-a")
    revoke_partner(reg, partner_id="prt-a", revocation_reason="x")
    assert reg.all_trusted() == []


# ── Token round-trip ───────────────────────────────────────────────


def test_token_roundtrip_recovers_payload():
    secret = generate_shared_secret()
    payload = {"op_kind": "outbound_citation", "reference_id": "xref-1"}
    tok = generate_partner_token(shared_secret_hex=secret, payload=payload)
    recovered = verify_partner_token(shared_secret_hex=secret, token=tok)
    assert recovered == payload


def test_tampered_payload_rejected():
    secret = generate_shared_secret()
    tok = generate_partner_token(
        shared_secret_hex=secret, payload={"op": "ok"},
    )
    # Flip a byte in the payload portion.
    parts = tok.split(".")
    bad_hex_payload = "ee" + parts[1][2:]  # different first byte
    tampered = ".".join([parts[0], bad_hex_payload, parts[2], parts[3], parts[4]])
    assert verify_partner_token(shared_secret_hex=secret, token=tampered) is None


def test_tampered_signature_rejected():
    secret = generate_shared_secret()
    tok = generate_partner_token(
        shared_secret_hex=secret, payload={"op": "ok"},
    )
    parts = tok.split(".")
    bad_sig = "0" * len(parts[4])
    tampered = ".".join([parts[0], parts[1], parts[2], parts[3], bad_sig])
    assert verify_partner_token(shared_secret_hex=secret, token=tampered) is None


def test_wrong_secret_rejected():
    a = generate_shared_secret()
    b = generate_shared_secret()
    tok = generate_partner_token(
        shared_secret_hex=a, payload={"op": "ok"},
    )
    assert verify_partner_token(shared_secret_hex=b, token=tok) is None


def test_expired_token_rejected():
    secret = generate_shared_secret()
    # Issued 10 minutes ago with a 5-minute TTL → expired even after skew.
    tok = generate_partner_token(
        shared_secret_hex=secret,
        payload={"op": "ok"},
        ttl_seconds=DEFAULT_TOKEN_TTL_SECONDS,
        issued_at_unix=1_000_000,
    )
    # now is 10 minutes + skew past issuance.
    assert verify_partner_token(
        shared_secret_hex=secret,
        token=tok,
        now_unix=1_000_000 + DEFAULT_TOKEN_TTL_SECONDS + DEFAULT_CLOCK_SKEW_SECONDS + 1,
    ) is None


def test_token_within_skew_window_accepted():
    secret = generate_shared_secret()
    tok = generate_partner_token(
        shared_secret_hex=secret,
        payload={"op": "ok"},
        ttl_seconds=DEFAULT_TOKEN_TTL_SECONDS,
        issued_at_unix=1_000_000,
    )
    # Slightly inside skew at the expiry edge → accepted.
    recovered = verify_partner_token(
        shared_secret_hex=secret,
        token=tok,
        now_unix=1_000_000 + DEFAULT_TOKEN_TTL_SECONDS + (DEFAULT_CLOCK_SKEW_SECONDS - 1),
    )
    assert recovered == {"op": "ok"}


def test_token_from_future_rejected():
    secret = generate_shared_secret()
    # iat is far in the future relative to now → reject as future-token.
    tok = generate_partner_token(
        shared_secret_hex=secret, payload={"op": "ok"},
        issued_at_unix=2_000_000,
    )
    assert verify_partner_token(
        shared_secret_hex=secret, token=tok, now_unix=1_000_000,
    ) is None


def test_malformed_token_rejected():
    secret = generate_shared_secret()
    for bad in ("", "notatoken", "v1.short", "v2.x.x.x.x", "v1.zz.0.0.zz"):
        assert verify_partner_token(shared_secret_hex=secret, token=bad) is None


def test_empty_secret_raises():
    with pytest.raises(PartnerIdentityError):
        verify_partner_token(shared_secret_hex="", token="anything")


def test_invalid_secret_hex_raises():
    secret = generate_shared_secret()
    tok = generate_partner_token(shared_secret_hex=secret, payload={"op": "ok"})
    with pytest.raises(PartnerIdentityError):
        verify_partner_token(shared_secret_hex="not-hex-zzz", token=tok)


def test_shared_secret_is_64_hex_chars():
    s = generate_shared_secret()
    # 32 bytes → 64 hex chars
    assert len(s) == 64
    int(s, 16)  # parses as hex
