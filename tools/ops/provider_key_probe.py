"""Make one bounded, direct authenticated probe of a provider key candidate.

The live EnvironmentFile mode checks the file's selected key directly, but
does not prove what a running process loaded or what BYOK currently supplies.
Complex or quoted selected values fail closed; this tool does not source or
fully implement systemd EnvironmentFile syntax.
"""

from __future__ import annotations

import argparse
import grp
import importlib
import os
import re
import stat
import sys
from pathlib import Path
from typing import TextIO

import httpx
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

OpenAICompatProvider = importlib.import_module(
    "substrate.dispatch.providers.openai_compat",
).OpenAICompatProvider

_TARGETS = {
    "zai": {
        "key_name": "Z_AI_API_KEY",
        "default_url": "https://api.z.ai/api/paas/v4",
        "url_env": "ANTIEK_ZAI_BASE_URL",
        "model": "glm-5.2",
        "path": "/chat/completions",
        "extra_body": {"thinking": {"type": "disabled"}},
    },
    "deepseek": {
        "key_name": "DEEPSEEK_API_KEY",
        "default_url": "https://api.deepseek.com",
        "url_env": "ANTIEK_DEEPSEEK_BASE_URL",
        "model": "deepseek-v4-pro",
        "path": "/v1/chat/completions",
        "extra_body": None,
    },
    "xiaomi": {
        "key_name": "XIAOMI_API_KEY",
        "default_url": "https://api.mimo.xiaomi.com/v1",
        "url_env": "ANTIEK_XIAOMI_BASE_URL",
        "model": "mimo-v2.5-pro",
        "path": "/chat/completions",
        "extra_body": None,
    },
}
_KEY_VALUE = re.compile(r"^[A-Za-z0-9_+./=-]+$")
_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_LIVE_ENV_FILE = Path("/etc/antiek/secrets.env")
_CONFIG_FILE = Path(__file__).resolve().parents[2] / "substrate/dispatch/config.yaml"


class ProbeInputError(ValueError):
    """A safe-to-display input error that never embeds file contents."""


def _read_candidate_key(path: Path, expected_name: str) -> str:
    """Read one exact KEY=value assignment without sourcing shell syntax."""
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError:
        raise ProbeInputError("cannot open key file") from None
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise ProbeInputError("key file must be a regular file")
        if info.st_uid not in (0, os.getuid()) or stat.S_IMODE(info.st_mode) != 0o600:
            raise ProbeInputError("key file must be owned by root or this user and have mode 0600")
        if info.st_size > 4096:
            raise ProbeInputError("key file is too large")
        with os.fdopen(fd, "r", encoding="ascii", newline="") as stream:
            fd = -1
            contents = stream.read(4097)
    except (OSError, UnicodeError):
        raise ProbeInputError("key file is unreadable or not plain ASCII") from None
    finally:
        if fd >= 0:
            os.close(fd)

    if len(contents) > 4096 or "\r" in contents:
        raise ProbeInputError("key file has invalid formatting")
    lines = contents.splitlines()
    if len(lines) != 1:
        raise ProbeInputError("key file must contain exactly one KEY=value line")
    name, sep, value = lines[0].partition("=")
    if not sep or name != expected_name or not value or not _KEY_VALUE.fullmatch(value):
        raise ProbeInputError(f"key file must contain one valid {expected_name}=value assignment")
    return value


def _read_live_env_key(path: Path, expected_name: str) -> str:
    """Read one selected unquoted assignment from root-owned EnvironmentFile.

    Blank lines, full-line comments, and ordinary NAME=value assignments are
    accepted; lines without '=' are ignored as systemd does. Values for
    unrelated names are ignored when their quotes close on the same physical
    line. Open quotes and physical continuations are rejected because they
    could consume the selected assignment. The selected value must be a
    single unquoted token; escapes, expansion, inline comments, and systemd's
    other value forms are intentionally unsupported.
    """
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError:
        raise ProbeInputError("cannot open live environment file") from None
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise ProbeInputError("live environment file must be a regular file")
        mode = stat.S_IMODE(info.st_mode)
        if info.st_uid != 0:
            raise ProbeInputError("live environment file must be root-owned")
        if mode == 0o640:
            try:
                antiek_gid = grp.getgrnam("antiek").gr_gid
            except KeyError:
                raise ProbeInputError("required antiek group is unavailable") from None
            if info.st_gid != antiek_gid:
                raise ProbeInputError("mode-0640 live environment file must belong to group antiek")
        elif mode != 0o600:
            raise ProbeInputError("live environment file must have mode 0600 or root:antiek mode 0640")
        if info.st_size > 65536:
            raise ProbeInputError("live environment file is too large")
        with os.fdopen(fd, "r", encoding="ascii", newline="") as stream:
            fd = -1
            contents = stream.read(65537)
    except (OSError, UnicodeError):
        raise ProbeInputError("live environment file is unreadable or not plain ASCII") from None
    finally:
        if fd >= 0:
            os.close(fd)

    if len(contents) > 65536 or "\r" in contents:
        raise ProbeInputError("live environment file has invalid formatting")
    found: list[str] = []
    for raw_line in contents.splitlines():
        if raw_line.rstrip().endswith("\\"):
            raise ProbeInputError("live environment file line continuations are unsupported")
        stripped = raw_line.lstrip()
        if not stripped or stripped.startswith(("#", ";")):
            continue
        name, sep, value = raw_line.partition("=")
        if not sep:
            continue
        if not _ENV_NAME.fullmatch(name):
            raise ProbeInputError("live environment file contains an unsupported assignment")
        if _has_open_quote(value):
            raise ProbeInputError("live environment file multiline quoted values are unsupported")
        if name != expected_name:
            continue
        found.append(value)
    if not found:
        raise ProbeInputError(f"live environment file does not contain {expected_name}")
    if len(found) != 1:
        raise ProbeInputError(f"live environment file contains duplicate {expected_name} assignments")
    value = found[0]
    if not value or not _KEY_VALUE.fullmatch(value):
        raise ProbeInputError(f"live {expected_name} must be one unquoted, simple token")
    return value


def _has_open_quote(value: str) -> bool:
    quote: str | None = None
    escaped = False
    for character in value:
        if escaped:
            escaped = False
            continue
        if character == "\\" and quote == '"':
            escaped = True
            continue
        if quote is None:
            if character in ("'", '"'):
                quote = character
        elif character == quote:
            quote = None
    return quote is not None


def _make_provider(name: str, key: str) -> OpenAICompatProvider:
    target = _TARGETS[name]
    override = os.environ.get(target["url_env"])
    if override is not None and override != target["default_url"]:
        raise ProbeInputError(f"refusing noncanonical endpoint override for {name}")
    base_url = target["default_url"]
    return OpenAICompatProvider(
        name=name,
        base_url=base_url,
        api_key=key,
        chat_completions_path=target["path"],
        extra_body=target["extra_body"],
        expose_error_body=False,
        timeout_s=10.0,
    )


def _verify_configured_model(name: str) -> None:
    """Refuse probing if config.yaml no longer names this provider model."""
    try:
        config = yaml.safe_load(_CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        raise ProbeInputError("cannot read provider models from substrate/dispatch/config.yaml") from None

    models: set[str] = set()

    def collect(value) -> None:
        if isinstance(value, dict):
            if value.get("provider") == name and isinstance(value.get("model"), str):
                models.add(value["model"])
            for child in value.values():
                collect(child)
        elif isinstance(value, list):
            for child in value:
                collect(child)

    collect(config)
    if models != {_TARGETS[name]["model"]}:
        raise ProbeInputError(f"probe model for {name} does not exactly match config.yaml")


def _probe(name: str, key: str, client=None) -> None:
    target = _TARGETS[name]
    _verify_configured_model(name)
    provider = _make_provider(name, key)
    # Disable ambient proxy settings so they cannot redirect the Authorization
    # header to a host selected through the caller's environment.
    provider._client = client if client is not None else httpx.Client(timeout=10.0, trust_env=False)
    provider._owns_client = client is None
    try:
        # No router or fallback chain is involved. The prompt and response
        # allowance are deliberately tiny; response content is never printed.
        provider.call(
            model=target["model"],
            prompt="Reply with OK.",
            max_tokens=8,
            temperature=0,
        )
    finally:
        provider.close()


def main(argv: list[str] | None = None, *, stdout: TextIO = sys.stdout, stderr: TextIO = sys.stderr) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("provider", choices=sorted(_TARGETS))
    key_source = parser.add_mutually_exclusive_group(required=True)
    key_source.add_argument("--key-file", type=Path,
                            help="0600 file containing only the selected provider's KEY=value assignment")
    key_source.add_argument("--live-env", action="store_true",
                            help="read the selected key from root-owned /etc/antiek/secrets.env")
    args = parser.parse_args(argv)
    key_name = _TARGETS[args.provider]["key_name"]
    try:
        if args.live_env:
            key = _read_live_env_key(_LIVE_ENV_FILE, key_name)
            source_label = "the live EnvironmentFile key"
        else:
            key = _read_candidate_key(args.key_file, key_name)
            source_label = "a candidate key read from the supplied file"
    except ProbeInputError as exc:
        print(f"Input error: {exc}", file=stderr)
        return 2
    try:
        _probe(args.provider, key)
    except ProbeInputError as exc:
        print(f"Configuration error: {exc}", file=stderr)
        return 2
    except Exception:
        print(f"Probe failed for {args.provider}; upstream details were suppressed.", file=stderr)
        return 1
    print(f"Probe succeeded for {args.provider} using {source_label}.", file=stdout)
    print("This does not prove the running service loaded this value or verify BYOK state.", file=stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
