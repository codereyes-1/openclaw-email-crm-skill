"""Synthetic JSON adapter used for demos, tests, and adapter development."""

import json
from pathlib import Path
from typing import Iterable

from .base import NormalizedMessageRecord


class SyntheticJsonAdapter:
    name = "synthetic-json-v1"

    def __init__(self, path: str):
        self.path = Path(path)

    def iter_messages(self) -> Iterable[NormalizedMessageRecord]:
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        records = payload.get("messages") if isinstance(payload, dict) else payload
        if not isinstance(records, list):
            raise ValueError("synthetic input must be a list or an object with a messages list")
        for index, item in enumerate(records):
            if not isinstance(item, dict):
                raise ValueError(f"message {index} must be an object")
            required = ("external_id", "conversation_external_id", "occurred_at", "direction")
            missing = [key for key in required if not item.get(key)]
            if missing:
                raise ValueError(f"message {index} missing required fields: {', '.join(missing)}")
            recipients = item.get("recipients", [])
            metadata = item.get("metadata", {})
            if not isinstance(recipients, list) or not all(isinstance(value, str) for value in recipients):
                raise ValueError(f"message {index} recipients must be a list of strings")
            if not isinstance(metadata, dict):
                raise ValueError(f"message {index} metadata must be an object")
            yield NormalizedMessageRecord(
                provider=item.get("provider", "synthetic"),
                account_ref=item.get("account_ref", "demo"),
                external_id=item["external_id"],
                conversation_external_id=item["conversation_external_id"],
                occurred_at=item["occurred_at"],
                direction=item["direction"],
                sender=item.get("sender"),
                recipients=tuple(recipients),
                subject=item.get("subject"),
                rfc_message_id=item.get("rfc_message_id"),
                excerpt=item.get("excerpt"),
                content_hash=item.get("content_hash"),
                metadata=metadata,
            )
