from __future__ import annotations

import hashlib
import hmac
from typing import Any

from app.core.config import settings


def verify_signature(*, raw_body: bytes, signature_header: str | None) -> bool:
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    supplied = signature_header.split("=", 1)[1].strip()
    expected = hmac.new(
        settings.whatsapp_app_secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(supplied, expected)


def payload_hash(raw_body: bytes) -> str:
    return hashlib.sha256(raw_body).hexdigest()


def extract_text_messages(payload: dict[str, Any]) -> list[dict[str, str]]:
    extracted: list[dict[str, str]] = []
    for entry in payload.get("entry", []) or []:
        for change in entry.get("changes", []) or []:
            value = change.get("value") or {}
            metadata = value.get("metadata") or {}
            phone_number_id = str(metadata.get("phone_number_id") or "")
            display_phone_number = str(metadata.get("display_phone_number") or "")
            contacts = {
                str(item.get("wa_id") or ""): str((item.get("profile") or {}).get("name") or "")
                for item in (value.get("contacts") or [])
            }
            for message in value.get("messages", []) or []:
                message_type = str(message.get("type") or "")
                if message_type != "text":
                    continue
                provider_event_id = str(message.get("id") or "")
                sender = str(message.get("from") or "")
                text = str((message.get("text") or {}).get("body") or "").strip()
                if phone_number_id and provider_event_id and sender and text:
                    extracted.append(
                        {
                            "phone_number_id": phone_number_id,
                            "display_phone_number": display_phone_number,
                            "provider_event_id": provider_event_id,
                            "from": sender,
                            "profile_name": contacts.get(sender, ""),
                            "text": text,
                        }
                    )
    return extracted
