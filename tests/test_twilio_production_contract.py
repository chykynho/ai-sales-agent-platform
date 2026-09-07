import base64

import pytest
from twilio.request_validator import RequestValidator

from app.voice.mulaw import decode_mulaw_sample, mulaw_rms, mulaw_to_pcm16, mulaw_to_wav
from app.voice.twilio_protocol import (
    TWILIO_MEDIA_FRAME_BYTES,
    TwilioProtocolError,
    build_bidirectional_twiml,
)


def test_twilio_sdk_request_validator_available():
    validator = RequestValidator("smoke-token")
    signature = validator.compute_signature(
        "https://voice.example.test/api/v1/channels/voice/twilio/incoming/demo",
        {"CallSid": "CA123", "From": "+5511999999999"},
    )
    assert signature
    assert validator.validate(
        "https://voice.example.test/api/v1/channels/voice/twilio/incoming/demo",
        {"CallSid": "CA123", "From": "+5511999999999"},
        signature,
    )


def test_production_twiml_contains_status_callback_and_parameters():
    xml = build_bidirectional_twiml(
        stream_url="wss://voice.example.test/api/v1/channels/voice/twilio/media/demo",
        status_callback_url="https://voice.example.test/api/v1/channels/voice/twilio/stream-status/demo",
        stream_name="ai-sales-agent",
        custom_parameters={
            "provider_account_id": "demo",
            "from_address": "+5511999999999",
        },
    )
    assert '<Connect><Stream ' in xml
    assert 'statusCallbackMethod="POST"' in xml
    assert 'name="ai-sales-agent"' in xml
    assert '<Parameter name="provider_account_id" value="demo" />' in xml
    assert '<Parameter name="from_address" value="+5511999999999" />' in xml


def test_production_twiml_rejects_insecure_callback():
    with pytest.raises(TwilioProtocolError):
        build_bidirectional_twiml(
            stream_url="wss://voice.example.test/media",
            status_callback_url="http://voice.example.test/status",
        )


def test_mulaw_silence_is_near_zero():
    silence = b"\xff" * TWILIO_MEDIA_FRAME_BYTES
    assert decode_mulaw_sample(0xFF) == 0
    assert mulaw_rms(silence) == 0


def test_mulaw_audio_conversion_produces_pcm_and_wav():
    raw = base64.b64decode("/////////////////////w==")
    pcm = mulaw_to_pcm16(raw)
    wav = mulaw_to_wav(raw)
    assert len(pcm) == len(raw) * 2
    assert wav.startswith(b"RIFF")
    assert b"WAVE" in wav[:16]
