"""Fail-closed inventory contract for routes exposed to normal accounts."""

from interfaces.research.api.app import create_app, is_multi_user_safe_route


def test_every_application_route_has_an_explicit_authorization_class():
    app = create_app(register_wrestling=False, register_providers=False, cors_origins=[])
    public = {
        ("GET", "/health"),
        ("POST", "/auth/request"),
        ("GET", "/auth/callback"),
        ("POST", "/auth/logout"),
        ("GET", "/auth/dev-login"),
        ("GET", "/.well-known/mcp-tools.json"),
    }
    inventory: dict[tuple[str, str], str] = {}
    for route in app.routes:
        path = getattr(route, "path", "")
        for method in getattr(route, "methods", set()):
            key = (method, path)
            if key in public or path.startswith("/speak/invite/") or method == "OPTIONS":
                inventory[key] = "public_or_token_scoped"
            elif is_multi_user_safe_route(method, path):
                inventory[key] = "user_safe"
            else:
                inventory[key] = "operator_only_default_deny"

    assert inventory
    assert set(inventory.values()) <= {
        "public_or_token_scoped",
        "user_safe",
        "operator_only_default_deny",
    }
    assert inventory[("POST", "/thought-partner")] == "user_safe"
    assert inventory[("POST", "/events/typed")] == "operator_only_default_deny"
