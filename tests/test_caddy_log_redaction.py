from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_CADDYFILE = _REPO / "infrastructure/ansible/templates/Caddyfile.j2"
_DEPLOY = _REPO / "infrastructure/ansible/playbooks/deploy.yml"


def test_caddy_access_log_deletes_cloudflare_access_headers() -> None:
    caddyfile = _CADDYFILE.read_text(encoding="utf-8")

    assert "format filter {" in caddyfile
    assert "request>headers>Cf-Access-Client-Id delete" in caddyfile
    assert "request>headers>Cf-Access-Client-Secret delete" in caddyfile
    assert "wrap json" in caddyfile


def test_deploy_never_reads_or_prints_caddy_access_log() -> None:
    deploy = _DEPLOY.read_text(encoding="utf-8")

    assert "/var/log/caddy/access.log" not in deploy
    assert "tail caddy access log" not in deploy.lower()
    assert "print caddy access log" not in deploy.lower()
