"""The unauthenticated /health probe must not publish user-derived state.

Measured live on the deployed build, with no credentials:

    registered_providers = ["deepseek", "hermes", "user-80946f0b-my-deepseek",
                            "user-80946f0b-my-xiaomi-mimo", ...]
    turbopuffer_content_hash = "41e399443ee69c7c305636a0f456d103054413dc19af323e4dadcf47011988ef"
    backup_marker_path = "/home/antiek/.antiek/backup_freshness.json"

A registered provider id can be `user-<operator-user-id>-<their-configured-provider-name>`,
so that list published a user identifier AND that user's own provider configuration.
"""

from __future__ import annotations

from interfaces.research.api.app import _PRIVATE_PROVIDER_PREFIX, _probe_backup_freshness


def test_the_backup_probe_publishes_no_filesystem_path() -> None:
    """A host path is not health information and this route needs no credentials."""
    verdict = _probe_backup_freshness()

    assert verdict["backup_marker_path"] == ""


def test_the_backup_probe_failure_does_not_leak_exception_text(monkeypatch) -> None:
    """The freshness evaluator raises with the marker path in the message.

    The previous form interpolated `str(exc)`, so a failure of the probe that exists to
    report absence was itself a way to read a host path anonymously.
    """
    import interfaces.research.api.app as app_mod
    import tools.backup_freshness as bf

    def _boom(*_args, **_kwargs):
        raise PermissionError("/srv/private/backup.json")

    monkeypatch.setattr(bf, "resolve_marker_path", _boom)

    verdict = app_mod._probe_backup_freshness()

    assert verdict["backup_marker_path"] == ""
    reason = str(verdict["backup_reason"])
    assert "/srv/private" not in reason
    assert "PermissionError" in reason


def test_user_derived_provider_ids_are_excluded_by_the_published_prefix() -> None:
    """The filter the route applies. Kept as a property so it cannot be dropped quietly."""
    names = ["deepseek", "hermes", "user-80946f0b-my-deepseek", "user-abc-my-xiaomi"]
    published = sorted(n for n in names if not n.startswith(_PRIVATE_PROVIDER_PREFIX))

    assert published == ["deepseek", "hermes"]
    assert not any("user-" in n for n in published)
