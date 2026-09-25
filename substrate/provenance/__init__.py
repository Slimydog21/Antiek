"""Provenance — shared reference validation (the KDL slice) AND the
bite-level provenance store (reformat-provenance SPR-01)."""

from .validate_refs import validate_ref, validate_refs

__all__ = ["validate_ref", "validate_refs"]
