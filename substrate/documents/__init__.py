"""substrate.documents — the document-lifecycle family (forks first).

The graph's ``documents`` table (substrate/graph/schema.py) is the store this
package writes; the modules that PRODUCE documents (ingest, acquisition,
reformat) stay where they are. What lives here is document-level lifecycle
machinery that spans those producers — unit 5's fork primitive is the first
member.
"""
