import base64

import pytest

from app.voice.twilio_protocol import (
    TWILIO_MEDIA_ENCODING,
    TWILIO_MEDIA_FRAME_BYTES,
    TWILIO_MEDIA_SAMPLE_RATE,
    TwilioProtocolError,
    build_bidirectional_twiml,
    build_clear_message,
    build_mark_message,
    build_media_message,
    iter_mulaw_frames,
    parse_media_message,
    parse_start_message,
)


def test_twilio_contract_and_media_payload():
    assert TWILIO_MEDIA_ENCODING == "audio/x-mulaw"
    assert TWILIO_MEDIA_SAMPLE_RATE == 8000
    raw = b"\xff" * TWILIO_MEDIA_FRAME_BYTES
    event = parse_media_message({
        "event": "media",
        "streamSid": "MZ123",
        "media": {"payload": base64.b64encode(raw).decode("ascii")},
    })
    assert event["audio_bytes"] == TWILIO_MEDIA_FRAME_BYTES
    assert event["audio"] == raw
    assert event["stream_sid"] == "MZ123"


def test_twiml_requires_secure_websocket():
    xml = build_bidirectional_twiml(stream_url="wss://voice.example.test/media")
    assert "<Connect><Stream" in xml
    assert "wss://voice.example.test/media" in xml
    with pytest.raises(TwilioProtocolError):
        build_bidirectional_twiml(stream_url="ws://insecure.example.test/media")


def test_bidirectional_outbound_messages_and_frames():
    raw = bytes(range(256)) * 2
    frames = list(iter_mulaw_frames(raw))
    assert frames
    assert all(0 < len(frame) <= TWILIO_MEDIA_FRAME_BYTES for frame in frames)
    media = build_media_message(stream_sid="MZ123", audio=frames[0])
    assert media["event"] == "media"
    assert base64.b64decode(media["media"]["payload"]) == frames[0]
    assert build_mark_message(stream_sid="MZ123", name="done")["event"] == "mark"
    assert build_clear_message(stream_sid="MZ123")["event"] == "clear"


def test_start_contract_requires_mulaw_8khz_mono():
    parsed = parse_start_message({
        "event": "start",
        "streamSid": "MZ123",
        "start": {
            "streamSid": "MZ123",
            "callSid": "CA123",
            "accountSid": "AC123",
            "mediaFormat": {"encoding": "audio/x-mulaw", "sampleRate": 8000, "channels": 1},
            "customParameters": {"provider_account_id": "demo"},
        },
    })
    assert parsed["call_sid"] == "CA123"
    assert parsed["custom_parameters"]["provider_account_id"] == "demo"
