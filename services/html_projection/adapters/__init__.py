"""Doc-model adapters (HPRJ SPR-05+).

Adapters map substrate-resident records (a synthesis row + its resolved
provenance) into the doc-model JSON the SPR-02 renderer accepts. The
rights filter lives IN the adapter, not the caller, so no path can reach
the renderer with unfiltered third-party text.
"""
