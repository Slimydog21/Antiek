"""End-to-end integration tests for antiek-unified.

The one suite that exercises the *composition* of the four product workflows —
not any single seam in isolation. ``test_flywheel.py`` drives a single graph
entity through Research → Read → Write → Speak → Read across the real SPR-03
typed seams and asserts it is one node id with unbroken provenance at every hop
(SPR-08 M1). It is the warrant for the master spec's central claim — "four
products are one product" — at the integration level.
"""
