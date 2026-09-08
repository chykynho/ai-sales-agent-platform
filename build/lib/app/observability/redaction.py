from __future__ import annotations

import re
from typing import Any

SENSITIVE_KEYS = {
    "authorization",
    "cookie",
    "set-cookie",
    "password",
    "secret",
    "token",
    "api_key",
    "apikey",
    "access_token",
    "refresh_token",
    "openai_api_key",
    "twilio_auth_token",
}
PHONE_RE = re.compile(r"(?<!\d)(\+?\d{8,15})(?!\d)")


def redact_value(key: str, value: Any) -> Any:
    normalized = key.lower().replace("-", "_")
    if any(sensitive in normalized for sensitive in SENSITIVE_KEYS):
        return "***REDACTED***"
    if isinstance(value, str):
        return PHONE_RE.sub("***PHONE***", value)
    return value
