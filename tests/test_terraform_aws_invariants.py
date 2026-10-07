"""Offline invariants for the AWS production + lane-host infrastructure.

Covers infrastructure/terraform-aws/ (both roots), the two Ansible hunks it
depends on, and the arm64 readiness verdict that picks the production
instance type. Nothing here needs AWS credentials or the network:

- the .tf text is read directly, so the security invariants hold even where
  terraform is not installed (CI);
- where terraform IS on PATH, `fmt -check`, `validate` and the mocked
  `terraform test` suites run as well. Those suites evaluate the rendered
  cloud-config, counts, budget filters and preconditions, which text checks
  cannot see;
- the arm64 gate walks uv.lock for exactly the extras deploy_atomic.yml
  installs, so a dependency without a linux-aarch64 wheel fails here instead
  of at the first deploy to a Graviton host.

Decision record: docs/decisions/aws-production-and-agent-backbone-2026-10-07.md.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest
import yaml

_REPO = Path(__file__).resolve().parents[1]
_TF = _REPO / "infrastructure" / "terraform-aws"
_ROOTS = (_TF, _TF / "bootstrap")
_ANSIBLE = _REPO / "infrastructure" / "ansible"
_SETUP = _ANSIBLE / "playbooks" / "setup.yml"
_DEPLOY = _ANSIBLE / "playbooks" / "deploy_atomic.yml"
_CADDYFILE = _ANSIBLE / "templates" / "Caddyfile.j2"
_BOOTSTRAP = _TF / "scripts" / "lane-host-bootstrap.sh"
_FAILSAFE = _TF / "scripts" / "lane-host-failsafe.sh"
_LANE_RUNBOOK = _REPO / "infrastructure" / "runbooks" / "lane-host.md"

_REGION = "eu-north-1"


# ── .tf text helpers ─────────────────────────────────────────────────────────


def _strip_comments(text: str) -> str:
    """Drop # and // comments that start a line or follow whitespace, which
    leaves "#cloud-config" and "https://" inside strings alone."""
    return "\n".join(re.sub(r"(^|\s)(#|//).*$", "", line) for line in text.splitlines())


def _tf_text(root: Path) -> str:
    return "\n".join(
        _strip_comments(p.read_text(encoding="utf-8")) for p in sorted(root.glob("*.tf"))
    )


def _blocks(text: str, kind: str, rtype: str | None) -> dict[str, str]:
    """name -> body for every `<kind> "<rtype>" "<name>" { ... }`, or for
    `<kind> "<name>" { ... }` when rtype is None (brace-balanced)."""
    out: dict[str, str] = {}
    head = rf'^{kind} "{re.escape(rtype)}" "([^"]+)" \{{' if rtype else rf'^{kind} "([^"]+)" \{{'
    for m in re.finditer(head, text, re.M):
        depth, i = 1, m.end()
        while depth:
            depth += {"{": 1, "}": -1}.get(text[i], 0)
            i += 1
        out[m.group(1)] = text[m.end() : i - 1]
    return out


def _all_tf() -> str:
    return "\n".join(_tf_text(root) for root in _ROOTS)


def test_both_roots_exist_and_are_not_empty() -> None:
    for root in _ROOTS:
        assert len(list(root.glob("*.tf"))) >= 3, f"{root} lost its .tf files"
    assert _blocks(_tf_text(_TF), "resource", "aws_instance").keys() == {"prod", "lane_host"}


def test_no_ingress_except_tcp_22_and_never_80_or_443() -> None:
    text = _all_tf()
    assert "aws_security_group_rule" not in text, "use aws_vpc_security_group_*_rule resources only"
    for name, body in _blocks(text, "resource", "aws_security_group").items():
        assert not re.search(r"^\s*ingress\s*\{", body, re.M), (
            f"inline ingress in aws_security_group.{name}"
        )
    rules = _blocks(text, "resource", "aws_vpc_security_group_ingress_rule")
    assert rules, "the prod SSH rule disappeared; this check would be vacuous"
    for name, body in rules.items():
        ports = {int(p) for p in re.findall(r"(?:from_port|to_port)\s*=\s*(\d+)", body)}
        assert ports == {22}, f"ingress rule {name} opens {ports}"
        assert re.search(r'ip_protocol\s*=\s*"tcp"', body), f"ingress rule {name} is not tcp"
        assert "aws_security_group.prod.id" in body, f"ingress rule {name} is not on the prod SG"
    assert not re.search(r"\b(80|443)\b", "\n".join(rules.values()))


def test_lane_host_security_group_has_no_ingress() -> None:
    text = _all_tf()
    lane_sg = _blocks(text, "resource", "aws_security_group")["lane_host"]
    assert "ingress" not in lane_sg
    for name, body in _blocks(text, "resource", "aws_vpc_security_group_ingress_rule").items():
        assert "lane_host" not in body, f"ingress rule {name} targets the lane-host SG"


def test_every_instance_requires_imdsv2_with_hop_limit_1() -> None:
    instances = _blocks(_tf_text(_TF), "resource", "aws_instance")
    for name, body in instances.items():
        assert re.search(r'http_tokens\s*=\s*"required"', body), (
            f"aws_instance.{name} allows IMDSv1"
        )
        assert re.search(r"http_put_response_hop_limit\s*=\s*1\b", body), (
            f"aws_instance.{name} hop limit"
        )
    defaults = _blocks(
        _tf_text(_TF / "bootstrap"), "resource", "aws_ec2_instance_metadata_defaults"
    )
    assert defaults and re.search(r'http_tokens\s*=\s*"required"', next(iter(defaults.values())))


def test_every_ebs_volume_is_encrypted() -> None:
    text = _tf_text(_TF)
    volumes = _blocks(text, "resource", "aws_ebs_volume")
    assert set(volumes) == {"prod_data", "lane_data"}
    for name, body in volumes.items():
        assert re.search(r"encrypted\s*=\s*true", body), f"aws_ebs_volume.{name} is not encrypted"
    for name, body in _blocks(text, "resource", "aws_instance").items():
        root = re.search(r"root_block_device\s*\{([^}]*)\}", body)
        assert root and re.search(r"encrypted\s*=\s*true", root.group(1)), (
            f"aws_instance.{name} root volume"
        )
    assert re.search(
        r"enabled\s*=\s*true",
        _blocks(_tf_text(_TF / "bootstrap"), "resource", "aws_ebs_encryption_by_default")["this"],
    )


def test_prod_data_volume_cannot_be_destroyed_by_a_plan() -> None:
    body = _blocks(_tf_text(_TF), "resource", "aws_ebs_volume")["prod_data"]
    assert re.search(r"prevent_destroy\s*=\s*true", body)
    assert re.search(r"final_snapshot\s*=\s*true", body)
    prod = _blocks(_tf_text(_TF), "resource", "aws_instance")["prod"]
    assert re.search(r"disable_api_termination\s*=\s*true", prod)
    assert re.search(r"disable_api_stop\s*=\s*true", prod)


def test_prod_state_dir_mount_path_is_exact() -> None:
    # TurboPuffer's servable pointer hashes the resolved DuckDB path
    # (substrate/graph/retrieval_adapters/turbopuffer.py), and group_vars
    # derives the state dir from the user name: they must agree exactly.
    group_vars = yaml.safe_load((_ANSIBLE / "group_vars" / "all.yml").read_text(encoding="utf-8"))
    derived = group_vars["antiek_state_dir"].replace("{{ antiek_user }}", group_vars["antiek_user"])
    assert re.search(rf'prod_state_dir\s*=\s*"{re.escape(derived)}"', _tf_text(_TF))
    assert derived == "/home/antiek/.antiek"


def test_backend_is_s3_with_native_locking_in_the_project_region() -> None:
    versions = _strip_comments((_TF / "versions.tf").read_text(encoding="utf-8"))
    backend = re.search(r'backend "s3" \{([^}]*)\}', versions)
    assert backend, "main root lost its S3 backend"
    assert re.search(r"use_lockfile\s*=\s*true", backend.group(1))
    assert re.search(r"encrypt\s*=\s*true", backend.group(1))
    assert re.search(rf'region\s*=\s*"{_REGION}"', backend.group(1))
    assert "backend " not in _tf_text(_TF / "bootstrap"), "bootstrap keeps local state by design"
    for root in _ROOTS:
        region = _blocks(_tf_text(root), "variable", None)["region"]
        assert re.search(rf'default\s*=\s*"{_REGION}"', region), (
            f"{root.name} region default drifted"
        )
    assert _REGION in (_TF / "backend.hcl.example").read_text(encoding="utf-8")


def test_lane_host_budgets_can_fire_and_the_cap_stops_and_unwakes() -> None:
    text = _tf_text(_TF)
    variables = _blocks(text, "variable", None)
    assert re.search(r"default\s*=\s*250\b", variables["lane_host_monthly_budget_usd"]), (
        "operator-approved cap is USD 250"
    )
    # L17: one r8g.xlarge for 744 h is USD 186.43, so an alert above that can
    # never fire. The alerting budget must sit at expected spend.
    expected = float(
        re.search(r"default\s*=\s*([\d.]+)", variables["lane_host_expected_monthly_usd"]).group(1)
    )
    assert expected < 744 * 0.25058 * 0.8, (
        "the lane-host alert cannot fire for a host stuck running"
    )
    budgets = _blocks(text, "resource", "aws_budgets_budget")
    assert "var.lane_host_expected_monthly_usd" in budgets["lane_host"]
    assert "local.lane_host_cap_usd" in budgets["lane_host_cap"]
    assert re.search(
        r"lane_host_cap_usd\s*=\s*var\.lane_host_monthly_budget_usd\s*-\s*var\.lane_host_count\s*\*\s*local\.lane_host_fixed_usd\s*-\s*var\.lane_host_egress_allowance_usd",
        text,
    ), "the cap must leave room for the fixed costs its filter cannot see"
    actions = _blocks(text, "resource", "aws_budgets_budget_action")
    stop, unwake = actions["stop_lane_hosts"], actions["block_lane_host_wake"]
    assert '"STOP_EC2_INSTANCES"' in stop and '"AUTOMATIC"' in stop
    assert "aws_instance.lane_host[*].id" in stop and "lane_host_cap[0]" in stop
    assert '"APPLY_IAM_POLICY"' in unwake and "aws_iam_role.lane_host_wake[0].name" in unwake
    policy = _blocks(text, "data", "aws_iam_policy_document")["budget_action"]
    assert re.search(r'"aws:ResourceTag/Role"[^]]*"lane-host"', policy, re.S), (
        "stop must be tag-scoped to lane hosts"
    )
    # The resources AWS's own budget-action policy lists (v2, 2026-04-07);
    # with the automation definition alone SSM denies the execution.
    for resource in (
        "document/AWS-StopEC2Instance",
        "automation-definition/AWS-StopEC2Instance:*",
        "automation-execution/*",
    ):
        assert resource in policy, f"budget-action role lacks {resource}"
    assert "AWS-StartEC2Instance" not in policy, "the cap role must never start instances"
    wake = _blocks(text, "data", "aws_iam_policy_document")["lane_host_wake"]
    assert '"ec2:StartInstances"' in wake and re.search(
        r'"aws:ResourceTag/Role"[^]]*"lane-host"', wake, re.S
    )


def test_prod_role_cannot_read_lane_host_parameters() -> None:
    # SSM core allows ssm:GetParameter* on "*"; only an explicit Deny keeps an
    # internet-facing host away from the tailnet join key.
    text = _tf_text(_TF)
    deny = _blocks(text, "data", "aws_iam_policy_document")["prod_deny_lane_host_params"]
    assert re.search(r'effect\s*=\s*"Deny"', deny)
    assert '"ssm:GetParameter"' in deny and '"ssm:GetParametersByPath"' in deny
    assert "local.tailscale_authkey_param_arn" in deny
    attach = _blocks(text, "resource", "aws_iam_role_policy")["prod_deny_lane_host_params"]
    assert "aws_iam_role.prod.id" in attach


_SECRET_PATTERNS = {
    "aws access key id": re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b"),
    "aws secret key assignment": re.compile(r"(?i)aws_secret_access_key\s*="),
    "tailscale auth key": re.compile(r"tskey-[a-z]+-[A-Za-z0-9]+"),
    "private key block": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "cloudflared tunnel secret": re.compile(r"TunnelSecret"),
    "12-digit account id": re.compile(r"(?<![0-9A-Za-z])(?!123456789012)[0-9]{12}(?![0-9A-Za-z])"),
}


def test_no_literal_secrets_or_account_ids_in_terraform_aws() -> None:
    files = [
        p
        for p in _TF.rglob("*")
        if p.is_file()
        and ".terraform" not in p.parts
        and p.suffix in {".tf", ".hcl", ".sh", ".example", ".md"}
    ]
    assert len(files) >= 15, "file discovery broke; the scan would be vacuous"
    for path in files:
        text = path.read_text(encoding="utf-8")
        for label, pattern in _SECRET_PATTERNS.items():
            match = pattern.search(text)
            assert match is None, f"{label} in {path.relative_to(_REPO)}: {match.group(0)[:12]}..."


def test_tailscale_key_is_read_at_boot_never_templated() -> None:
    text = _tf_text(_TF)
    assert "tailscale_authkey_param" in text
    assert not re.search(r'variable "tailscale_auth_?key"', text), (
        "the key itself must never be a variable"
    )
    bootstrap = _BOOTSTRAP.read_text(encoding="utf-8")
    assert "--with-decryption" in bootstrap and '--auth-key="file:$keyfile"' in bootstrap
    # Single use: deleted after the join, so no instance role can read it later.
    assert bootstrap.index("tailscale up") < bootstrap.index("ssm delete-parameter")
    lane_role = _blocks(text, "data", "aws_iam_policy_document")["lane_host_tailscale_key"]
    assert '"ssm:DeleteParameter"' in lane_role


def test_lane_host_bootstrap_bounds_every_wait_and_arms_the_sweep_before_the_network() -> None:
    """L11/L21: runcmd runs once per instance, so a step that hangs or fails
    must not leave a host that never stops. The sweep (idle poweroff) is on
    before anything that talks to the network, and every external wait has a
    bound."""
    body = _strip_comments(_BOOTSTRAP.read_text(encoding="utf-8"))
    sweep = body.index("systemctl enable --now compute-lane-host-sweep.timer")
    for later in ("apt-get update", "snap wait", "ssm get-parameter", "tailscale up"):
        assert sweep < body.index(later), f"the sweep is armed after {later!r}"
    for cmd in (
        "curl ",
        "apt-get update",
        "apt-get install",
        "snap wait",
        "snap install",
        "/snap/bin/aws",
    ):
        for line in (
            ln for ln in body.splitlines() if cmd in ln and not ln.lstrip().startswith("--")
        ):
            assert "timeout " in line, f"unbounded wait: {line.strip()}"
    assert re.search(r"tailscale up[^\n]*\n(?:[^\n]*\\\n)*[^\n]*--timeout=", body), (
        "tailscale up has no --timeout"
    )
    assert "--accept-dns=false" in body
    assert "ufw deny out on tailscale0" in body, "lane code must not reach the tailnet (the Mini)"
    assert (
        body.rstrip().splitlines()[-2].startswith('date -u +%FT%TZ > "$state_dir/provisioned"')
    ), "the provisioned marker must be the last step"


def test_lane_host_runcmd_arms_the_failsafe_first() -> None:
    lane = _strip_comments((_TF / "lane_host.tf").read_text(encoding="utf-8"))
    runcmd = re.search(r"runcmd = \[(.*?)\n\s*\]\n", lane, re.S)
    assert runcmd, "lane-host runcmd not found"
    steps = runcmd.group(1)
    assert (
        steps.index("lane-host-failsafe.timer")
        < steps.index("attach-data-volume")
        < steps.index("lane-host-bootstrap")
    )


def test_lane_host_user_data_edit_is_not_a_replacement() -> None:
    body = _blocks(_tf_text(_TF), "resource", "aws_instance")["lane_host"]
    assert re.search(r"user_data_replace_on_change\s*=\s*false", body)


def test_idle_poweroff_has_exactly_one_owner() -> None:
    lane = _tf_text(_TF)
    assert "idle-stop" not in lane and "idle_stop.sh" not in lane
    assert not (_TF / "scripts" / "lanes-idle-stop.sh").exists()
    assert "idle_poweroff_min = var.lane_host_idle_stop_minutes" in lane
    assert "ExecStart=${local.lane_host_helper_path} sweep" in lane


def test_saved_plans_are_gitignored() -> None:
    if shutil.which("git") is None:
        pytest.skip("git not available")
    for rel in ("tfplan", "bootstrap/tfplan", "x.tfplan"):
        r = subprocess.run(
            ["git", "check-ignore", "-q", str(_TF / rel)],
            cwd=_REPO,
            capture_output=True,
            timeout=30,
        )
        assert r.returncode == 0, f"infrastructure/terraform-aws/{rel} is not ignored (public repo)"


def _compute_policy() -> tuple[dict, Path] | None:
    path = Path(
        os.environ.get("COMPUTE_POLICY", Path.home() / ".agents" / "compute" / "policy.yaml")
    )
    if not path.is_file():
        return None
    policy = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return (policy, path) if (policy.get("hosts") or {}).get("nodes") else None


def _tf_default(text: str, name: str) -> str:
    body = _blocks(text, "variable", None)[name]
    return re.search(r'default\s*=\s*("[^"]*"|[\d.]+|\[[^]]*\])', body).group(1)


def test_lane_host_matches_the_compute_contract() -> None:
    """compute owns the host contract (policy.yaml hosts.nodes + backends.node,
    bin/compute-lane-host); this root installs it. Runs wherever a compute
    policy with a hosts.nodes entry exists (COMPUTE_POLICY, else
    ~/.agents/compute/policy.yaml); CI has none and skips."""
    found = _compute_policy()
    if found is None:
        pytest.skip(
            "no compute policy with hosts.nodes (COMPUTE_POLICY / ~/.agents/compute/policy.yaml)"
        )
    policy, path = found
    text = _tf_text(_TF)
    prefix = json.loads(_tf_default(text, "lane_host_name_prefix"))
    name, node = next(
        (n, h) for n, h in sorted(policy["hosts"]["nodes"].items()) if n.endswith("-1")
    )
    backend = policy["backends"]["node"]
    local = {
        k: json.loads(v)
        for k, v in re.findall(r'^\s*(lane_host_[a-z_]+)\s*=\s*("[^"]*")\s*$', text, re.M)
    }
    assert name == f"{prefix}-1", f"policy host {name} != {prefix}-1"
    assert node["ssh"] == f"{local['lane_host_control_user']}@{name}"
    assert node["workroot"] == local["lane_host_workroot"]
    assert node["slice"] == local["lane_host_slice"]
    assert backend["helper"] == local["lane_host_helper_path"]
    assert node["region"] == json.loads(_tf_default(text, "region"))
    assert node["instance_type"] == json.loads(_tf_default(text, "lane_host_instance_type"))
    assert float(node["budget_usd_month"]) == float(
        _tf_default(text, "lane_host_monthly_budget_usd")
    )
    assert set(node["keys"]) <= set(json.loads(_tf_default(text, "lane_host_provider_keys")))
    projects = set(
        re.findall(
            r"^\s*([a-z0-9_-]+)\s*=\s*\{ retention",
            _blocks(text, "variable", None)["lane_host_projects"],
            re.M,
        )
    )
    assert set(node["projects"]) == projects
    runbook = _LANE_RUNBOOK.read_text(encoding="utf-8")
    assert backend["ssh_identity"] in runbook, "the runbook must create the key compute pins"
    assert node["prime_agent"] in runbook
    example = path.parent / "bin" / "compute-lane-host.example.json"
    if example.is_file():
        config = re.search(r"lane_host_helper_config = jsonencode\(\{(.*?)\}\)", text, re.S)
        assert config, "lane-host.json is no longer rendered"
        rendered = set(re.findall(r"^\s*([a-z_]+)\s*=", config.group(1), re.M))
        assert set(json.loads(example.read_text(encoding="utf-8"))) <= rendered


# ── Ansible hunks this root depends on ───────────────────────────────────────


def test_rclone_build_follows_the_host_cpu() -> None:
    tasks = yaml.safe_load(_SETUP.read_text(encoding="utf-8"))[0]["tasks"]
    select = next(
        t for t in tasks if t.get("name") == "select the pinned rclone build for this CPU"
    )
    builds = select["vars"]["rclone_builds"]
    # Both from rclone's PGP-signed SHA256SUMS for v1.75.1 (checked 2026-10-07).
    assert builds == {
        "x86_64": {
            "name": "rclone-v1.75.1-linux-amd64",
            "sha256": "982b5aa772841168f8e380f139e9e787b2a105403e32b94da8676a0e1c0a13ab",
        },
        "aarch64": {
            "name": "rclone-v1.75.1-linux-arm64",
            "sha256": "03f2504174034b6d004152ed7369251c9a9ec1f7e0836eda420f5c7a5ec0dff9",
        },
    }
    fetch = next(t for t in tasks if t.get("name") == "fetch pinned rclone zip (checksum-verified)")
    assert fetch["ansible.builtin.get_url"]["checksum"] == "sha256:{{ rclone_build.sha256 }}"
    assert "linux-amd64" not in json.dumps([t for t in tasks if t is not select])


def _render_caddyfile(**extra: str) -> str:
    jinja2 = pytest.importorskip("jinja2")
    # Ansible's template module renders with trim_blocks=True.
    env = jinja2.Environment(trim_blocks=True, undefined=jinja2.StrictUndefined)
    variables = {
        "ansible_managed": "Ansible managed",
        "api_domain": "api.antiek.ai",
        "frontend_dist_dir": "/opt/antiek/frontend-dist",
        "uvicorn_port": 8001,
    }
    return env.from_string(_CADDYFILE.read_text(encoding="utf-8")).render(**variables, **extra)


def _site_block(rendered: str) -> str:
    start = rendered.index("api.antiek.ai {")
    return rendered[start : rendered.index("@api_routes", start)]


def test_caddy_origin_tls_selection() -> None:
    default = _site_block(_render_caddyfile())
    assert "import /etc/caddy/origin-tls.d/*.caddy" in default
    assert not re.search(r"^\s*tls ", default, re.M)
    internal = _site_block(_render_caddyfile(caddy_origin_tls="internal"))
    assert re.search(r"^    tls internal$", internal, re.M)
    assert not re.search(r"^\s*import ", internal, re.M)


def _prod_origin_tls_snippet() -> str:
    prod = (_TF / "prod.tf").read_text(encoding="utf-8")
    m = re.search(
        r'path\s*=\s*"/etc/caddy/origin-tls\.d/internal\.caddy".*?<<-EOT\n(.*?)\n\s*EOT', prod, re.S
    )
    assert m, "prod cloud-init no longer writes the origin-tls snippet Caddyfile.j2 imports"
    return "\n".join(line.strip() for line in m.group(1).splitlines()) + "\n"


def test_prod_cloud_init_declares_tls_internal() -> None:
    assert re.search(r"^tls internal$", _prod_origin_tls_snippet(), re.M)


@pytest.mark.skipif(shutil.which("caddy") is None, reason="caddy not on PATH")
def test_caddy_adapts_hetzner_unchanged_and_aws_to_the_internal_issuer(tmp_path: Path) -> None:
    """The default render on a host WITHOUT the snippet dir adapts to the same
    config as the template without the import line (the Hetzner box keeps its
    exact behaviour); with the cloud-init snippet it gains the internal issuer.
    """

    def adapt(caddyfile: str, name: str) -> dict:
        d = tmp_path / name
        d.mkdir()
        (d / "Caddyfile").write_text(caddyfile, encoding="utf-8")
        env = {
            **os.environ,
            "XDG_DATA_HOME": str(tmp_path / "data"),
            "XDG_CONFIG_HOME": str(tmp_path / "cfg"),
        }
        out = subprocess.run(
            ["caddy", "adapt", "--config", "Caddyfile", "--adapter", "caddyfile"],
            cwd=d,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
            check=True,
        )
        return json.loads(out.stdout)

    snippet_dir = tmp_path / "origin-tls.d"
    default = _render_caddyfile().replace("/etc/caddy/origin-tls.d", str(tmp_path / "absent"))
    stripped = re.sub(
        r"^\s*import /etc/caddy/origin-tls\.d/\*\.caddy\n", "", _render_caddyfile(), flags=re.M
    )
    assert stripped != _render_caddyfile()
    assert adapt(default, "default") == adapt(stripped, "stripped")
    assert "tls" not in adapt(default, "default2")["apps"]

    snippet_dir.mkdir()
    (snippet_dir / "internal.caddy").write_text(_prod_origin_tls_snippet(), encoding="utf-8")
    aws = adapt(_render_caddyfile().replace("/etc/caddy/origin-tls.d", str(snippet_dir)), "aws")
    explicit = adapt(_render_caddyfile(caddy_origin_tls="internal"), "explicit")
    for cfg in (aws, explicit):
        assert cfg["apps"]["tls"]["automation"]["policies"] == [
            {"subjects": ["api.antiek.ai"], "issuers": [{"module": "internal"}]}
        ]
    assert aws["apps"]["http"]["servers"].keys() == explicit["apps"]["http"]["servers"].keys()


def test_aws_inventory_example_matches_the_deploy_contract() -> None:
    text = (_ANSIBLE / "inventory.aws.ini.example").read_text(encoding="utf-8")
    hosts = [
        ln
        for ln in text.splitlines()
        if ln and not ln.startswith(("#", "[", ";")) and "ansible_host=" in ln
    ]
    assert len(hosts) == 1 and "ansible_user=root" in hosts[0]
    assert re.search(r"^caddy_origin_tls=internal$", text, re.M)
    assert "[antiek_prod]" in text and "[antiek_prod:vars]" in text


# ── arm64 readiness of the production dependency closure ────────────────────


def _deploy_extras() -> list[str]:
    plays = yaml.safe_load(_DEPLOY.read_text(encoding="utf-8"))

    def walk(tasks):
        for task in tasks:
            yield task
            for key in ("block", "rescue", "always"):
                yield from walk(task.get(key, []))

    sync = next(
        t
        for t in walk(plays[1]["tasks"])
        if t.get("name") == "exact-sync the service venv from the gated SHA's lock"
    )
    argv = sync["ansible.builtin.command"]["argv"]
    return [argv[i + 1] for i, arg in enumerate(argv) if arg == "--extra"]


def _prod_closure(arch: str) -> list[dict]:
    """Packages `uv sync --frozen --extra <prod extras>` installs on linux/<arch>, cp312.

    Cross-checked 2026-10-07 against `uv export --frozen --no-dev` with the
    same extras and markers evaluated for linux: the same 118 packages.
    """
    pytest.importorskip("packaging")
    from packaging.markers import Marker
    from packaging.utils import canonicalize_name

    env = {
        "sys_platform": "linux",
        "platform_system": "Linux",
        "os_name": "posix",
        "platform_machine": arch,
        "python_version": "3.12",
        "python_full_version": "3.12.3",
        "implementation_name": "cpython",
        "platform_python_implementation": "CPython",
        "platform_release": "",
        "platform_version": "",
        "implementation_version": "3.12.3",
        "extra": "",
    }
    lock = tomllib.loads((_REPO / "uv.lock").read_text(encoding="utf-8"))
    by_name: dict[str, list[dict]] = {}
    for pkg in lock["package"]:
        by_name.setdefault(canonicalize_name(pkg["name"]), []).append(pkg)

    def resolve(dep: dict) -> dict:
        candidates = by_name[canonicalize_name(dep["name"])]
        if len(candidates) == 1:
            return candidates[0]
        matches = [
            c
            for c in candidates
            if dep.get("version", c["version"]) == c["version"]
            and dep.get("source", c["source"]) == c["source"]
        ]
        assert len(matches) == 1, f"ambiguous lock entry for {dep}"
        return matches[0]

    root = by_name["antiek"][0]
    optional = {canonicalize_name(k): v for k, v in root.get("optional-dependencies", {}).items()}
    pending = list(root.get("dependencies", []))
    for extra in _deploy_extras():
        pending += optional[canonicalize_name(extra)]
    seen: dict[tuple[str, str], set[str]] = {}
    while pending:
        dep = pending.pop()
        if dep.get("marker") and not Marker(dep["marker"]).evaluate(env):
            continue
        pkg = resolve(dep)
        key = (canonicalize_name(pkg["name"]), pkg["version"])
        new_extras = set(dep.get("extra", [])) - seen.get(key, set())
        if key in seen and not new_extras:
            continue
        if key not in seen:
            pending += pkg.get("dependencies", [])
        seen.setdefault(key, set()).update(new_extras)
        pkg_optional = {
            canonicalize_name(k): v for k, v in pkg.get("optional-dependencies", {}).items()
        }
        for extra in new_extras:
            pending += pkg_optional.get(canonicalize_name(extra), [])
    return [resolve({"name": n, "version": v}) for n, v in seen]


def _installable_on(arch: str, wheel: str, glibc: tuple[int, int] = (2, 39)) -> bool:
    """True for a py3/cp312/abi3 wheel whose platform is `any` or a manylinux
    tag for `arch` at or below Ubuntu 24.04's glibc (2.39). musllinux wheels
    do not install on glibc Ubuntu."""
    from packaging.utils import parse_wheel_filename

    legacy = {"manylinux1": (2, 5), "manylinux2010": (2, 12), "manylinux2014": (2, 17)}
    for tag in parse_wheel_filename(wheel)[3]:
        plat = tag.platform
        if plat == "any":
            plat_ok = True
        elif m := re.fullmatch(r"manylinux_(\d+)_(\d+)_(\w+)", plat):
            plat_ok = m.group(3) == arch and (int(m.group(1)), int(m.group(2))) <= glibc
        else:
            base, _, tail = plat.partition("_")
            plat_ok = tail == arch and legacy.get(base, (99, 0)) <= glibc
        interp_ok = (
            tag.interpreter in {"py3", "py312", "cp312", "py2.py3"}
            or (
                tag.abi == "abi3"
                and tag.interpreter.startswith("cp3")
                and int(tag.interpreter[3:]) <= 12
            )
            or (tag.interpreter.startswith("py3") and tag.abi == "none")
        )
        if plat_ok and interp_ok and tag.abi in {"none", "abi3", "cp312"}:
            return True
    return False


@pytest.mark.parametrize("arch", ["aarch64", "x86_64"])
def test_every_prod_dependency_has_a_linux_wheel_for_the_prod_arch(arch: str) -> None:
    closure = _prod_closure(arch)
    names = {p["name"] for p in closure}
    assert {"duckdb", "fastapi", "torch", "uvicorn", "turbopuffer"} <= names, (
        "closure walk is broken"
    )
    assert len(closure) > 60, f"only {len(closure)} packages: the walk lost the extras"
    blockers = []
    for pkg in closure:
        wheels = [w["url"].rsplit("/", 1)[1] for w in pkg.get("wheels", [])]
        if not any(_installable_on(arch, w) for w in wheels):
            blockers.append(
                f"{pkg['name']}=={pkg['version']} ({'sdist only' if 'sdist' in pkg else 'no artifact'})"
            )
    assert not blockers, f"no linux-{arch} wheel in uv.lock for: {blockers}"


# ── lane-host boot failsafe ─────────────────────────────────────────────────


@pytest.fixture
def failsafe(tmp_path: Path):
    """Run lane-host-failsafe.sh against a temporary state dir and stubs."""
    if shutil.which("bash") is None:
        pytest.skip("bash not available")
    stubs = tmp_path / "bin"
    stubs.mkdir()
    calls = tmp_path / "calls"
    mounted, timer = tmp_path / "mounted", tmp_path / "timer-active"
    (stubs / "systemctl").write_text(
        f'#!/bin/sh\nif [ "$1" = is-active ]; then [ -e "{timer}" ]; exit $?; fi\n'
        f'echo "systemctl $*" >> "{calls}"\n'
    )
    (stubs / "mountpoint").write_text(f'#!/bin/sh\n[ -e "{mounted}" ]\n')
    (stubs / "logger").write_text("#!/bin/sh\nexit 0\n")
    for stub in stubs.iterdir():
        stub.chmod(0o755)
    defaults = tmp_path / "defaults"
    defaults.write_text(f"LANES_WORKROOT={tmp_path / 'srv'}\n")
    state = tmp_path / "state"
    state.mkdir()
    env = {
        "PATH": f"{stubs}:/usr/bin:/bin",
        "LANE_HOST_DEFAULTS": str(defaults),
        "LANE_HOST_STATE_DIR": str(state),
    }

    def run() -> list[str]:
        subprocess.run(
            ["bash", str(_FAILSAFE)], env=env, check=True, timeout=30, capture_output=True
        )
        return calls.read_text().splitlines() if calls.exists() else []

    def healthy() -> None:
        (state / "provisioned").write_text("2026-10-07T00:00:00Z\n")
        mounted.touch()
        timer.touch()

    return run, healthy, state, mounted, timer


def test_failsafe_leaves_a_provisioned_mounted_sweeping_host_up(failsafe) -> None:
    run, healthy, *_ = failsafe
    healthy()
    assert run() == []


def test_failsafe_powers_off_when_the_bootstrap_never_finished(failsafe) -> None:
    # The finding's case: SSM parameter missing -> bootstrap exits -> no marker.
    run, healthy, state, *_ = failsafe
    healthy()
    (state / "provisioned").unlink()
    assert run() == ["systemctl poweroff"]


def test_failsafe_powers_off_without_the_data_volume(failsafe) -> None:
    run, healthy, _, mounted, _ = failsafe
    healthy()
    mounted.unlink()
    assert run() == ["systemctl poweroff"]


def test_failsafe_powers_off_when_nothing_would_idle_stop(failsafe) -> None:
    run, healthy, _, _, timer = failsafe
    healthy()
    timer.unlink()
    assert run() == ["systemctl poweroff"]


@pytest.mark.skipif(shutil.which("shellcheck") is None, reason="shellcheck not on PATH")
def test_cloud_init_scripts_pass_shellcheck() -> None:
    scripts = sorted((_TF / "scripts").glob("*.sh"))
    assert len(scripts) == 3
    subprocess.run(["shellcheck", "-s", "bash", *map(str, scripts)], check=True, timeout=60)


# ── terraform itself, when installed ─────────────────────────────────────────


def _terraform(root: Path, *args: str, timeout: int = 600) -> subprocess.CompletedProcess:
    env = {**os.environ, "TF_IN_AUTOMATION": "1", "CHECKPOINT_DISABLE": "1"}
    return subprocess.run(
        ["terraform", *args], cwd=root, env=env, capture_output=True, text=True, timeout=timeout
    )


@pytest.mark.skipif(shutil.which("terraform") is None, reason="terraform not on PATH")
@pytest.mark.parametrize("root", _ROOTS, ids=["main", "bootstrap"])
def test_terraform_fmt_validate_and_offline_tests(root: Path) -> None:
    """fmt and validate need no provider credentials; `terraform test` runs the
    mocked suites in <root>/tests (mock_provider: no account, no API calls).
    init downloads the pinned provider once if it is not cached."""
    fmt = _terraform(root, "fmt", "-check", "-recursive", "-no-color")
    assert fmt.returncode == 0, f"terraform fmt -check failed:\n{fmt.stdout}{fmt.stderr}"
    init = _terraform(root, "init", "-backend=false", "-input=false", "-no-color")
    if init.returncode != 0 and "registry.terraform.io" in init.stderr:
        pytest.skip(f"provider not cached and registry unreachable: {init.stderr.strip()[-200:]}")
    assert init.returncode == 0, init.stderr
    validate = _terraform(root, "validate", "-no-color")
    assert validate.returncode == 0, validate.stdout + validate.stderr
    test = _terraform(root, "test", "-no-color")
    assert test.returncode == 0, test.stdout[-4000:] + test.stderr[-2000:]
    assert re.search(r"Success! [1-9]\d* passed, 0 failed", test.stdout), test.stdout[-2000:]
