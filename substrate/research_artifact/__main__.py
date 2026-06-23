"""CLI: python -m substrate.research_artifact <investigation_id>"""

from __future__ import annotations

import argparse
import sys

from .compose import compose_artifacts
from .export import export_research_artifact
from .import_notes import import_agent_notes


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Export ResearchArtifact HTML")
    p.add_argument(
        "investigation_ids",
        nargs="*",
        help="Investigation id(s) for export/compose",
    )
    p.add_argument(
        "--import-notes",
        metavar="PATH",
        help="Import append-only agent_notes from artifact HTML (SPR-AHT-03)",
    )
    p.add_argument(
        "--compose",
        action="store_true",
        help="Write compose index when multiple ids given",
    )
    p.add_argument("--no-event", action="store_true", help="Skip artifact.generated emit")
    args = p.parse_args(argv)
    if args.import_notes:
        from pathlib import Path

        res = import_agent_notes(Path(args.import_notes))
        print(
            f"imported={res.notes_imported} skipped_dup={res.notes_skipped_duplicate} "
            f"investigation={res.investigation_id}"
        )
        return 0
    if not args.investigation_ids:
        p.error("investigation_ids required unless --import-notes is set")
    if len(args.investigation_ids) > 1 and args.compose:
        res = compose_artifacts(args.investigation_ids)
        print(res.path)
        return 0
    for iid in args.investigation_ids:
        res = export_research_artifact(iid, emit_event=not args.no_event)
        print(res.path)
    return 0


if __name__ == "__main__":
    sys.exit(main())