"""Content-type-specific extractors for the ingestion pipeline.

Each extractor returns an ``ExtractedDocument`` (defined in
``pipeline.py``) — a uniform record the pipeline can chunk + embed
+ store regardless of the source format.
"""
