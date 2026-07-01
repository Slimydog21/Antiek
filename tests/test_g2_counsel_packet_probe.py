from __future__ import annotations

import json

from tools.ops import g2_counsel_packet_probe


def _packet() -> str:
    return """# G2 Counsel Packet

**Status:** operator-support packet; **does not close G2**.

The packet references `docs/decisions/g2-lawyer-review.md`.

## Summary

This covers pre-onboarded escrow, opt-in-only payout activation, and
costless opt-out. It points counsel at `substrate/ip_holders/__init__.py`,
`NOTIFICATION_EMAIL_TEMPLATE`, `docs/trust_center_public.md`, and
legal@antiek.ai.

## Legal context

Counsel should review Bartz v. Anthropic, Hachette v. Internet Archive,
and Google Books.
"""


def test_g2_counsel_packet_probe_passes_complete_packet(tmp_path):
    packet = tmp_path / "docs/g2_counsel_packet.md"
    packet.parent.mkdir(parents=True)
    packet.write_text(_packet(), encoding="utf-8")
    decision = tmp_path / "docs/decisions/g2-lawyer-review.md"

    result = g2_counsel_packet_probe.probe_g2_counsel_packet(
        packet_path=packet,
        decision_path=decision,
    )

    assert result.status == "PASS"
    assert result.does_not_close_oa001 is True


def test_g2_counsel_packet_probe_fails_missing_context(tmp_path):
    packet = tmp_path / "g2.md"
    packet.write_text("not enough", encoding="utf-8")

    result = g2_counsel_packet_probe.probe_g2_counsel_packet(
        packet_path=packet,
        decision_path=tmp_path / "decision.md",
    )

    checks = {check.name: check for check in result.checks}
    assert result.status == "FAIL"
    assert checks["packet_required_fragments"].passed is False
    assert "Bartz v. Anthropic" in checks["packet_required_fragments"].detail


def test_g2_counsel_packet_probe_reports_existing_decision(tmp_path):
    packet = tmp_path / "g2.md"
    packet.write_text(_packet(), encoding="utf-8")
    decision = tmp_path / "docs/decisions/g2-lawyer-review.md"
    decision.parent.mkdir(parents=True)
    decision.write_text("# decision\n", encoding="utf-8")

    result = g2_counsel_packet_probe.probe_g2_counsel_packet(
        packet_path=packet,
        decision_path=decision,
    )

    checks = {check.name: check for check in result.checks}
    assert result.status == "FAIL"
    assert checks["decision_not_already_filed"].passed is False


def test_g2_counsel_packet_probe_json_cli(tmp_path, capsys):
    packet = tmp_path / "g2.md"
    packet.write_text(_packet(), encoding="utf-8")

    exit_code = g2_counsel_packet_probe.main([
        "--packet-path",
        str(packet),
        "--decision-path",
        str(tmp_path / "decision.md"),
        "--json",
    ])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["status"] == "PASS"
    assert payload["does_not_close_oa001"] is True
