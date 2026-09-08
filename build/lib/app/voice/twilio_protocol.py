from __future__ import annotations

import base64
from html import escape
from typing import Iterable

TWILIO_MEDIA_ENCODING = "audio/x-mulaw"
TWILIO_MEDIA_SAMPLE_RATE = 8000
TWILIO_MEDIA_CHANNELS = 1
TWILIO_MEDIA_FRAME_MS = 20
TWILIO_MEDIA_FRAME_BYTES = 160  # 8 kHz * 20 ms * 1 byte/sample (mu-law)


class TwilioProtocolError(ValueError):
    pass


def parse_media_message(payload: dict) -> dict:
    event = str(payload.get("event") or "")
    if event not in {"connected", "start", "media", "mark", "dtmf", "stop"}:
        raise TwilioProtocolError(f"unsupported Twilio event: {event or '<missing>'}")
    if event == "media":
        media = payload.get("media") or {}
        encoded = media.get("payload")
        if not isinstance(encoded, str) or not encoded:
            raise TwilioProtocolError("Twilio media event requires media.payload")
        try:
            raw = base64.b64decode(encoded, validate=True)
        except Exception as exc:
            raise TwilioProtocolError("Twilio media payload is not valid base64") from exc
        return {"event": event, "audio_bytes": len(raw), "stream_sid": payload.get("streamSid"), "audio": raw}
    return {"event": event, "audio_bytes": 0, "stream_sid": payload.get("streamSid")}


def parse_start_message(payload: dict) -> dict:
    if str(payload.get("event") or "") != "start":
        raise TwilioProtocolError("expected Twilio start event")
    start = payload.get("start") or {}
    stream_sid = str(start.get("streamSid") or payload.get("streamSid") or "")
    call_sid = str(start.get("callSid") or "")
    media_format = start.get("mediaFormat") or {}
    if not stream_sid or not call_sid:
        raise TwilioProtocolError("Twilio start requires streamSid and callSid")
    if media_format:
        if str(media_format.get("encoding") or "") != TWILIO_MEDIA_ENCODING:
            raise TwilioProtocolError("Twilio Media Stream must use audio/x-mulaw")
        if int(media_format.get("sampleRate") or 0) != TWILIO_MEDIA_SAMPLE_RATE:
            raise TwilioProtocolError("Twilio Media Stream must use 8000 Hz")
        if int(media_format.get("channels") or 0) != TWILIO_MEDIA_CHANNELS:
            raise TwilioProtocolError("Twilio Media Stream must use one audio channel")
    return {
        "stream_sid": stream_sid,
        "call_sid": call_sid,
        "account_sid": str(start.get("accountSid") or ""),
        "custom_parameters": dict(start.get("customParameters") or {}),
    }


def iter_mulaw_frames(audio: bytes, *, frame_bytes: int = TWILIO_MEDIA_FRAME_BYTES) -> Iterable[bytes]:
    if frame_bytes <= 0:
        raise TwilioProtocolError("frame_bytes must be positive")
    for offset in range(0, len(audio), frame_bytes):
        chunk = audio[offset:offset + frame_bytes]
        if chunk:
            yield chunk


def build_media_message(*, stream_sid: str, audio: bytes) -> dict:
    if not stream_sid:
        raise TwilioProtocolError("stream_sid is required")
    if not audio:
        raise TwilioProtocolError("audio is required")
    return {
        "event": "media",
        "streamSid": stream_sid,
        "media": {"payload": base64.b64encode(audio).decode("ascii")},
    }


def build_mark_message(*, stream_sid: str, name: str) -> dict:
    if not stream_sid or not name:
        raise TwilioProtocolError("stream_sid and mark name are required")
    return {"event": "mark", "streamSid": stream_sid, "mark": {"name": name}}


def build_clear_message(*, stream_sid: str) -> dict:
    if not stream_sid:
        raise TwilioProtocolError("stream_sid is required")
    return {"event": "clear", "streamSid": stream_sid}


def build_bidirectional_twiml(
    *,
    stream_url: str,
    custom_parameters: dict[str, str] | None = None,
    status_callback_url: str | None = None,
    stream_name: str | None = None,
) -> str:
    if not stream_url.startswith("wss://"):
        raise TwilioProtocolError("Twilio bidirectional Media Streams require a wss:// URL")
    if status_callback_url and not status_callback_url.startswith("https://"):
        raise TwilioProtocolError("Twilio production statusCallback requires an https:// URL")
    attrs = [f'url="{escape(stream_url, quote=True)}"']
    if stream_name:
        attrs.append(f'name="{escape(stream_name, quote=True)}"')
    if status_callback_url:
        attrs.append(f'statusCallback="{escape(status_callback_url, quote=True)}"')
        attrs.append('statusCallbackMethod="POST"')
    params = ""
    for name, value in (custom_parameters or {}).items():
        clean_name = str(name).strip()
        if not clean_name:
            raise TwilioProtocolError("Twilio custom parameter name cannot be empty")
        params += (
            '<Parameter name="' + escape(clean_name, quote=True) + '" value="'
            + escape(str(value), quote=True) + '" />'
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Response><Connect><Stream ' + " ".join(attrs) + '>'
        + params + '</Stream></Connect></Response>'
    )
