"""Shared hosted-document application service."""

from .service import (
    HostAuthorization,
    HostedDocumentResult,
    ingest_hosted_document,
)

__all__ = ["HostAuthorization", "HostedDocumentResult", "ingest_hosted_document"]
