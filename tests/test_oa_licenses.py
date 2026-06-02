"""Tests for acquisition/openaccess/licenses.py (SPR-03 M2).

The OA license mapping shares the CC core with arXiv (``licenses_core``) and
adds the OA-specific rows. The load-bearing cases asserted directly:

  - bronze OA -> gated (free-to-read is NOT free-to-redistribute);
  - CC-BY / CC-BY-SA -> servable as source_declared_open (2026-05-29 remap);
  - CC0 -> servable as public_domain (2026-05-29 remap);
  - CC Public-Domain Mark -> servable as public_domain;
  - unknown / missing -> gated (deny-by-default).

Plus the structural guard the arXiv suite has: every resolution's
content_class is a member of substrate's _VALID_BOOK_CONTENT_CLASSES.
"""

from __future__ import annotations

import os
import sys

import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from acquisition.openaccess.licenses import (  # noqa: E402
    license_basis_string,
    resolve_oa_license,
)
from substrate.books.ingest import _VALID_BOOK_CONTENT_CLASSES  # noqa: E402
from substrate.constants import GATED_DEFAULT_CONTENT_CLASS  # noqa: E402

# ---------------------------------------------------------------------------
# Servable
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "uri",
    [
        "https://creativecommons.org/licenses/by/4.0/",
        "http://creativecommons.org/licenses/by/3.0/",
        "cc-by",  # OpenAlex/Unpaywall short form
    ],
)
def test_cc_by_is_servable(uri):
    r = resolve_oa_license(uri)
    assert r.redistributable is True
    # 2026-05-29 remap: CC-BY is source-declared-open, NOT a §9.10 publisher opt-in.
    assert r.content_class == "source_declared_open"


def test_cc_by_sa_is_servable():
    r = resolve_oa_license("https://creativecommons.org/licenses/by-sa/4.0/")
    assert r.redistributable is True
    # 2026-05-29 remap: CC-BY-SA is source-declared-open, NOT a §9.10 publisher opt-in.
    assert r.content_class == "source_declared_open"


def test_cc0_is_servable():
    r = resolve_oa_license("https://creativecommons.org/publicdomain/zero/1.0/")
    assert r.redistributable is True
    # 2026-05-29 remap: CC0 is a public-domain dedication -> public_domain.
    assert r.content_class == "public_domain"


def test_public_domain_mark_is_servable_public_domain():
    """CC Public-Domain Mark marks an already-public-domain work -> servable
    as public_domain. (Post-2026-05-29 remap, CC0 also lands in public_domain;
    PDM and CC0 now share the public_domain lane — both lack a rights holder.)"""
    r = resolve_oa_license("https://creativecommons.org/publicdomain/mark/1.0/")
    assert r.redistributable is True
    assert r.content_class == "public_domain"


# ---------------------------------------------------------------------------
# Gated — the OA-specific load-bearing case is BRONZE
# ---------------------------------------------------------------------------


def test_bronze_explicit_signal_is_gated():
    """Bronze OA: free-to-read on the publisher site, no open license. The
    cardinal OA trap — must NOT be servable."""
    r = resolve_oa_license("bronze")
    assert r.redistributable is False
    assert r.content_class == GATED_DEFAULT_CONTENT_CLASS
    assert "bronze" in r.license_name.lower()


def test_publisher_specific_is_gated():
    r = resolve_oa_license("publisher-specific")
    assert r.redistributable is False
    assert r.content_class == GATED_DEFAULT_CONTENT_CLASS


@pytest.mark.parametrize(
    "uri",
    [
        "https://creativecommons.org/licenses/by-nc/4.0/",
        "https://creativecommons.org/licenses/by-nc-nd/4.0/",
        "cc-by-nc",
    ],
)
def test_cc_by_nc_is_gated(uri):
    r = resolve_oa_license(uri)
    assert r.redistributable is False
    assert r.content_class == GATED_DEFAULT_CONTENT_CLASS


def test_cc_by_nd_is_gated():
    r = resolve_oa_license("https://creativecommons.org/licenses/by-nd/4.0/")
    assert r.redistributable is False
    assert r.content_class == GATED_DEFAULT_CONTENT_CLASS


def test_unknown_is_gated():
    """LOAD-BEARING: an unrecognised license is NEVER guessed servable."""
    r = resolve_oa_license("https://example.com/novel-license/9.9/")
    assert r.redistributable is False
    assert r.content_class == GATED_DEFAULT_CONTENT_CLASS


@pytest.mark.parametrize("missing", [None, "", "   "])
def test_missing_license_is_gated(missing):
    """Bronze typically arrives with NO license at all -> deny-by-default."""
    r = resolve_oa_license(missing)
    assert r.redistributable is False
    assert r.content_class == GATED_DEFAULT_CONTENT_CLASS


# ---------------------------------------------------------------------------
# Structural guard + basis string
# ---------------------------------------------------------------------------


def test_every_resolution_class_is_valid_book_content_class():
    """A typo in a content_class would crash register_book at ingest time;
    assert every row resolves to a class the substrate accepts."""
    sample = [
        "https://creativecommons.org/licenses/by/4.0/",
        "https://creativecommons.org/licenses/by-sa/4.0/",
        "https://creativecommons.org/publicdomain/zero/1.0/",
        "https://creativecommons.org/publicdomain/mark/1.0/",
        "https://creativecommons.org/licenses/by-nc/4.0/",
        "https://creativecommons.org/licenses/by-nd/4.0/",
        "bronze",
        "publisher-specific",
        "totally-unknown",
        None,
    ]
    for uri in sample:
        assert resolve_oa_license(uri).content_class in _VALID_BOOK_CONTENT_CLASSES


def test_basis_string_servable_names_license():
    r = resolve_oa_license("https://creativecommons.org/licenses/by/4.0/")
    basis = license_basis_string(r)
    assert "CC BY" in basis
    assert "creativecommons.org/licenses/by/4.0" in basis


def test_basis_string_bronze_states_why():
    r = resolve_oa_license("bronze")
    basis = license_basis_string(r)
    assert basis.startswith("GATED")
    assert "bronze" in basis.lower()
