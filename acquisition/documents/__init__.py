"""Format-neutral document extraction for canonical hosted HTML ingestion."""

from .extract import ExtractedDocument, ExtractedTocEntry, extract_document_bytes

__all__ = ["ExtractedDocument", "ExtractedTocEntry", "extract_document_bytes"]
