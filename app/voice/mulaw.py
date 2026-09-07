from __future__ import annotations

import io
import math
import struct
import wave


def decode_mulaw_sample(value: int) -> int:
    """Decodifica um byte G.711 mu-law para PCM16 assinado."""
    u = (~value) & 0xFF
    sign = u & 0x80
    exponent = (u >> 4) & 0x07
    mantissa = u & 0x0F
    sample = ((mantissa << 3) + 0x84) << exponent
    sample -= 0x84
    return -sample if sign else sample


def mulaw_to_pcm16(audio: bytes) -> bytes:
    out = bytearray()
    for value in audio:
        out.extend(struct.pack("<h", decode_mulaw_sample(value)))
    return bytes(out)


def mulaw_rms(audio: bytes) -> int:
    if not audio:
        return 0
    total = 0
    for value in audio:
        sample = decode_mulaw_sample(value)
        total += sample * sample
    return int(math.sqrt(total / len(audio)))


def mulaw_to_wav(audio: bytes, *, sample_rate: int = 8000) -> bytes:
    pcm = mulaw_to_pcm16(audio)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm)
    return buffer.getvalue()
