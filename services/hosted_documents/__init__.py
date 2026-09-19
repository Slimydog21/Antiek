"""Shared hosted-document application service."""

from .service import (
    EmitDocumentLoaded,
    HostAuthorization,
    HostedDocumentResult,
    ingest_hosted_document,
)

__all__ = [
    "EmitDocumentLoaded",
    "HostAuthorization",
    "HostedDocumentResult",
    "ingest_hosted_document",
]
