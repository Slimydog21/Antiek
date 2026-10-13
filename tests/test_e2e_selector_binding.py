"""An e2e spec must not bind to a selector the app no longer has.

No workflow runs the Playwright spec suite, so a deleted component leaves its
specs asserting against nothing and every board stays green. This lint is the
cheap static half of that problem.

Every test below that starts `test_control_` exists because this lint was WRONG
in that exact way during development. They are not decoration — the lint's first
run produced 13 findings of which 8 were false, and a later "fix" produced a
clean zero while a known-dead selector sat in the tree. A gate with no control
measures nothing.
"""
import json

import pytest

from tools.lint import e2e_selector_binding as lint


def test_no_new_unbound_selectors():
    assert lint.check() == []


# ---------------------------------------------------------------------------
# Controls — each one is a false positive or false negative this lint produced
# ---------------------------------------------------------------------------

def test_control_the_lint_scans_a_non_empty_spec_set():
    """A zero finding means nothing if the scan found no specs."""
    specs = lint._spec_files()
    assert len(specs) >= 20, f"only {len(specs)} spec files discovered"
    assert len(lint._source_blob()) > 100_000, "source blob suspiciously small"


def test_control_a_dead_selector_is_actually_caught(tmp_path, monkeypatch):
    """The lint returned a clean ZERO once while a dead selector was present.

    Cause: the locator regex captured `[^"']+`, but a single-quoted selector
    legitimately contains double quotes, so it truncated at the first inner
    quote and matched a harmless fragment.
    """
    spec_dir = tmp_path / "e2e"
    spec_dir.mkdir()
    (spec_dir / "dead.spec.ts").write_text(
        """test("x", async ({ page }) => {\n"""
        """  await page.locator('[data-testid="live-thing"] [data-totally-removed]').click();\n"""
        """});\n"""
    )
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "App.tsx").write_text('<div data-testid="live-thing" />')
    monkeypatch.setattr(lint, "E2E", spec_dir)
    monkeypatch.setattr(lint, "SRC", src_dir)
    monkeypatch.setattr(lint, "ROOT", tmp_path)

    found = lint.unbound_selectors()
    assert len(found) == 1 and "data-totally-removed" in found[0]


def test_control_a_template_literal_testid_is_not_flagged(tmp_path, monkeypatch):
    """`data-testid={`thread-hop-${wf}`}` never appears in source as a literal.

    Treating those as unbound produced 8 of this lint's first 13 findings.
    """
    spec_dir = tmp_path / "e2e"
    spec_dir.mkdir()
    (spec_dir / "t.spec.ts").write_text(
        """await page.getByTestId("thread-hop-write").click();\n"""
    )
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "Bread.tsx").write_text("<a data-testid={`thread-hop-${hop.workflow}`} />")
    monkeypatch.setattr(lint, "E2E", spec_dir)
    monkeypatch.setattr(lint, "SRC", src_dir)
    monkeypatch.setattr(lint, "ROOT", tmp_path)

    assert lint.unbound_selectors() == []


def test_control_a_union_with_one_live_side_is_not_flagged(tmp_path, monkeypatch):
    """`'[data-testid="x"], [data-legacy]'` binds if EITHER side does."""
    spec_dir = tmp_path / "e2e"
    spec_dir.mkdir()
    (spec_dir / "u.spec.ts").write_text(
        """await page.locator('[data-testid="mascot"], [data-legacy-mascot]').first();\n"""
    )
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "M.tsx").write_text('<b data-testid="mascot" />')
    monkeypatch.setattr(lint, "E2E", spec_dir)
    monkeypatch.setattr(lint, "SRC", src_dir)
    monkeypatch.setattr(lint, "ROOT", tmp_path)

    assert lint.unbound_selectors() == []


def test_control_a_self_injected_attribute_is_not_flagged(tmp_path, monkeypatch):
    """A spec that creates its own target legitimately has no source match."""
    spec_dir = tmp_path / "e2e"
    spec_dir.mkdir()
    (spec_dir / "i.spec.ts").write_text(
        """await page.evaluate(() => { b.setAttribute("data-product-id", "research"); });\n"""
        """await page.locator('[data-product-id]').click();\n"""
    )
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "S.tsx").write_text("<div />")
    monkeypatch.setattr(lint, "E2E", spec_dir)
    monkeypatch.setattr(lint, "SRC", src_dir)
    monkeypatch.setattr(lint, "ROOT", tmp_path)

    assert lint.unbound_selectors() == []


# ---------------------------------------------------------------------------
# Baseline hygiene
# ---------------------------------------------------------------------------

def test_baseline_is_shrink_only_and_explains_itself():
    data = json.loads(lint.BASELINE.read_text())
    assert "SHRINK-ONLY" in data["note"]
    assert data["reconsider_if"]
    assert data["provenance"]["base"]
    assert len(data["known_unbound"]) <= 2, (
        "the baseline grew — a new unbound selector must be fixed, not recorded"
    )


def test_a_fixed_baseline_entry_must_be_removed(monkeypatch):
    """A stale entry reds too, so the baseline cannot quietly outlive its debt."""
    monkeypatch.setattr(lint, "unbound_selectors", lambda: [])
    failures = lint.check()
    assert any("shrink the baseline" in failure for failure in failures)


@pytest.mark.parametrize("missing", ["note", "known_unbound"])
def test_baseline_has_required_keys(missing):
    assert missing in json.loads(lint.BASELINE.read_text())


def test_control_a_dead_css_rule_is_not_evidence_that_an_element_renders(tmp_path, monkeypatch):
    """A stylesheet declares how a class WOULD look; it does not render anything.

    The first version of this lint counted ``.css`` as source, so a rule left
    behind by a deleted component was itself the match. ``.werner-rig-flipper-r``
    survived only in ``src/werner/waddle.css`` after WernerRig was removed, and
    the spec binding it went unflagged — the lint was blind to exactly the case
    it exists for. Caught by a peer session deleting the orphaned stylesheet.
    """
    spec_dir = tmp_path / "e2e"
    spec_dir.mkdir()
    (spec_dir / "s.spec.ts").write_text(
        """await page.locator('.ghost-rig-foot').click();\n"""
    )
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    # Defined in CSS, rendered by nothing.
    (src_dir / "dead.css").write_text(".ghost-rig-foot { opacity: 0; }")
    (src_dir / "App.tsx").write_text("<div />")
    monkeypatch.setattr(lint, "E2E", spec_dir)
    monkeypatch.setattr(lint, "SRC", src_dir)
    monkeypatch.setattr(lint, "ROOT", tmp_path)

    found = lint.unbound_selectors()
    assert len(found) == 1 and "ghost-rig-foot" in found[0]
