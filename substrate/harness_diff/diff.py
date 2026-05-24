"""HarnessDiff -- semantic diff between two HarnessSnapshots."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from substrate.harness_diff.snapshot import HarnessSnapshot


@dataclass(frozen=True)
class HarnessDiff:
    a_tag: str
    b_tag: str
    seams_added: tuple[str, ...] = ()
    seams_removed: tuple[str, ...] = ()
    seams_changed: tuple[tuple[str, str, str], ...] = ()
    hooks_added: tuple[dict, ...] = ()
    hooks_removed: tuple[dict, ...] = ()
    model_config_changes: dict[str, tuple[Any, Any]] = field(default_factory=dict)
    tools_added: tuple[str, ...] = ()
    tools_removed: tuple[str, ...] = ()
    tools_changed: tuple[tuple[str, str, str], ...] = ()
    system_prompt_changed: bool = False
    substrate_version_changed: tuple[str, str] | None = None

    def is_empty(self) -> bool:
        return not (
            self.seams_added or self.seams_removed or self.seams_changed
            or self.hooks_added or self.hooks_removed or self.model_config_changes
            or self.tools_added or self.tools_removed or self.tools_changed
            or self.system_prompt_changed or self.substrate_version_changed
        )


def _hook_key(h: dict) -> tuple[str, str, str]:
    return (h.get("seam_id", ""), h.get("extension_id", ""), h.get("stage", ""))


def diff_snapshots(a: HarnessSnapshot, b: HarnessSnapshot) -> HarnessDiff:
    a_seams = a.hook_seams
    b_seams = b.hook_seams
    seams_added = tuple(sorted(set(b_seams) - set(a_seams)))
    seams_removed = tuple(sorted(set(a_seams) - set(b_seams)))
    seams_changed = tuple(
        sorted(
            (sid, a_seams[sid], b_seams[sid])
            for sid in (set(a_seams) & set(b_seams))
            if a_seams[sid] != b_seams[sid]
        )
    )

    a_hooks = {_hook_key(h): h for h in a.hooks}
    b_hooks = {_hook_key(h): h for h in b.hooks}
    hooks_added = tuple(b_hooks[k] for k in sorted(b_hooks.keys() - a_hooks.keys()))
    hooks_removed = tuple(a_hooks[k] for k in sorted(a_hooks.keys() - b_hooks.keys()))

    model_diffs: dict[str, tuple[Any, Any]] = {}
    for k in set(a.model_config) | set(b.model_config):
        av = a.model_config.get(k)
        bv = b.model_config.get(k)
        if av != bv:
            model_diffs[k] = (av, bv)

    a_tools = {t.get("name", ""): t.get("description", "") for t in a.tools}
    b_tools = {t.get("name", ""): t.get("description", "") for t in b.tools}
    tools_added = tuple(sorted(b_tools.keys() - a_tools.keys()))
    tools_removed = tuple(sorted(a_tools.keys() - b_tools.keys()))
    tools_changed = tuple(
        sorted(
            (n, a_tools[n], b_tools[n])
            for n in (a_tools.keys() & b_tools.keys())
            if a_tools[n] != b_tools[n]
        )
    )

    prompt_changed = a.system_prompt_digest != b.system_prompt_digest

    version_changed: tuple[str, str] | None = None
    if a.substrate_version != b.substrate_version:
        version_changed = (a.substrate_version, b.substrate_version)

    return HarnessDiff(
        a_tag=a.tag, b_tag=b.tag,
        seams_added=seams_added, seams_removed=seams_removed, seams_changed=seams_changed,
        hooks_added=hooks_added, hooks_removed=hooks_removed,
        model_config_changes=model_diffs,
        tools_added=tools_added, tools_removed=tools_removed, tools_changed=tools_changed,
        system_prompt_changed=prompt_changed,
        substrate_version_changed=version_changed,
    )
