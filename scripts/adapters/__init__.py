"""Provider adapter interfaces for normalized, read-only ingestion."""

from .base import MessageAdapter, NormalizedMessageRecord
from .synthetic import SyntheticJsonAdapter

__all__ = ["MessageAdapter", "NormalizedMessageRecord", "SyntheticJsonAdapter"]
