"""Human- and agent-facing command for the Mac-mini Herdr bridge."""

from __future__ import annotations

import argparse
import json
import os
import stat
import sys
from pathlib import Path

from .antiek_client import AntiekClient
from .config import BridgeConfig, load_config
from .daemon import BridgeDaemon
from .herdr_adapter import HerdrAdapter
from .journal import BridgeJournal
from .models import StructuredResult


def _private_result_file(path: Path, config: BridgeConfig) -> None:
    expected_parent = (config.journal_path.parent / "results").resolve()
    if path.parent.resolve() != expected_parent:
        raise ValueError("result JSON must be inside the configured private results directory")
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.getuid():
        raise PermissionError("result JSON must be an owner-controlled regular file")
    if stat.S_IMODE(info.st_mode) != 0o600:
        raise PermissionError("result JSON must have mode 0600")
    if info.st_size > 65_536:
        raise ValueError("result JSON exceeds 64 KiB")


def submit_result(config: BridgeConfig, result_path: str | Path) -> StructuredResult:
    path = Path(result_path).expanduser()
    _private_result_file(path, config)
    result = StructuredResult.parse(json.loads(path.read_text()))
    with BridgeJournal(config.journal_path) as journal:
        journal.capture_result(result)
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="herdr-bridge")
    parser.add_argument("--config", required=True)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("run")
    submit = commands.add_parser("submit-result")
    submit.add_argument("--result-json", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = load_config(args.config)
        if args.command == "submit-result":
            result = submit_result(config, args.result_json)
            print(json.dumps({"accepted": True, "work_id": result.work_id}))
            return 0
        with BridgeJournal(config.journal_path) as journal:
            daemon = BridgeDaemon(
                config,
                antiek=AntiekClient(config),
                herdr=HerdrAdapter(config=config),
                journal=journal,
            )
            daemon.run_forever()
    except KeyboardInterrupt:
        return 0
    except Exception as exc:
        print(f"herdr-bridge: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
