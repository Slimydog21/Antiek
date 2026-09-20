"""Production wiring for mutable user-model state."""

from pathlib import Path

_SERVICE = (
    Path(__file__).parents[1]
    / "infrastructure"
    / "ansible"
    / "templates"
    / "antiek.service.j2"
)


def test_byok_state_is_inside_the_systemd_write_boundary() -> None:
    service = _SERVICE.read_text(encoding="utf-8")

    for variable, suffix in (
        ("ANTIEK_BYOK_ARTIFACT", "byok/credentials.enc"),
        ("ANTIEK_BYOK_KEY_FILE", "byok/byok_master.key"),
        ("ANTIEK_USER_MODELS_PATH", "settings/user_models.json"),
    ):
        assert (
            f'Environment="{variable}={{{{ antiek_state_dir }}}}/{suffix}"'
            in service
        )

    assert "ReadWritePaths={{ antiek_state_dir }} /tmp /var/tmp" in service
