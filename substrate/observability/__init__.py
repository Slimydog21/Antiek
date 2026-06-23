"""Product observability shims (PostHog). DuckDB remains defensibility truth."""

from substrate.observability.posthog import capture, capture_distinct, is_enabled
from substrate.observability.product_mirror import mirror_layer_event

__all__ = ["capture", "capture_distinct", "is_enabled", "mirror_layer_event"]