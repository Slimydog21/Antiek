"""A banned host must be banned however the URL spells it (audit wave 3, #16)."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pytest

from substrate.legal_gate.predicate import url_blocked_reason

BANNED = ["libgen.is"]

def test_control_plain_banned_host_is_banned():
    assert url_blocked_reason("https://libgen.is/book/1", banned_domains=BANNED)

@pytest.mark.parametrize("url", [
    "https://libgen.is:443/book/1",        # explicit port
    "https://user@libgen.is/book/1",       # userinfo
    "https://libgen.is./book/1",           # DNS root trailing dot
    "https://USER:pw@LIBGEN.IS:8443./x",   # all three, upper-case
    "https://mirror.libgen.is:443/x",      # subdomain + port
])
def test_netloc_decorations_no_longer_bypass_the_ban(url):
    assert url_blocked_reason(url, banned_domains=BANNED), f"{url} slipped past the banned-domain gate"

def test_control_unbanned_host_is_allowed():
    assert url_blocked_reason("https://example.com/x", banned_domains=BANNED) is None

def test_unparseable_host_is_refused_not_allowed():
    # a netloc that yields no hostname must not read as "allowed"
    assert url_blocked_reason("https://:443/x", banned_domains=BANNED)
