"""Stable provider-neutral contract. Adapters fetch; they never mutate providers."""

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Optional, Protocol, Sequence


@dataclass(frozen=True)
class NormalizedMessageRecord:
    provider: str
    account_ref: str
    external_id: str
    conversation_external_id: str
    occurred_at: str
    direction: str
    sender: Optional[str] = None
    recipients: Sequence[str] = ()
    subject: Optional[str] = None
    rfc_message_id: Optional[str] = None
    excerpt: Optional[str] = None
    content_hash: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class MessageAdapter(Protocol):
    name: str

    def iter_messages(self) -> Iterable[NormalizedMessageRecord]:
        """Yield normalized records without writing, deleting, or sending provider data."""
