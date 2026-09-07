from __future__ import annotations

import audioop
import base64
import io
import json
import os
import random
import sys
import time
import unicodedata
import wave

import httpx
import websocket
from twilio.request_validator import RequestValidator

from app.core.config import settings
from app.voice.transcription_client import OpenAITranscriptionClient
from app.voice.twilio_protocol import TWILIO_MEDIA_FRAME_BYTES, iter_mulaw_frames

BASE_LOCAL = "http://127.0.0.1:8000/api/v1"
PUBLIC_BASE = os.environ.get("TWILIO_PUBLIC_BASE_URL", "https://voice.example.test").rstrip("/")
WSS_BASE = os.environ.get("TWILIO_WSS_BASE_URL", "wss://voice.example.test").rstrip("/")
TENANT = "demo"
ACCOUNT = "smoke-twilio-prod-demo-001"
ACCOUNT_SID = "ACSMOKEV011DEMO"
PHONE = "+5511000000001"
AUTH_ENV = "TWILIO_AUTH_TOKEN_SMOKE"
AUTH_TOKEN = os.environ.get(AUTH_ENV, "local-v011-twilio-auth-token")
SMOKE_TTS_MODEL = os.environ.get("OPENAI_SMOKE_TTS_MODEL", "gpt-4o-mini-tts-2025-12-15")
SMOKE_QUESTION = "Qual é o preço do plano PRO? Repito: qual é o preço do plano PRO?"


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return " ".join(normalized.lower().replace("-", " ").split())


def assert_smoke_question_transcribed(text: str) -> None:
    normalized = normalize_text(text)
    has_product = "pro" in normalized.split() or "plano pro" in normalized
    has_price_intent = any(token in normalized for token in ("preco", "custa", "valor"))
    if not (has_product and has_price_intent):
        raise AssertionError(
            "Audio sintetico nao foi transcrito com confianca suficiente para o teste de pricing. "
            f"Transcricao obtida: {text!r}"
        )


def wav_to_twilio_mulaw(wav_bytes: bytes) -> bytes:
    """Converte WAV PCM do endpoint Speech para G.711 mu-law mono/8 kHz do Twilio."""
    with wave.open(io.BytesIO(wav_bytes), "rb") as wav_file:
        channels = wav_file.getnchannels()
        sample_width = wav_file.getsampwidth()
        sample_rate = wav_file.getframerate()
        pcm = wav_file.readframes(wav_file.getnframes())

    if channels == 2:
        pcm = audioop.tomono(pcm, sample_width, 0.5, 0.5)
        channels = 1
    elif channels != 1:
        raise RuntimeError(f"TTS WAV com quantidade de canais nao suportada: {channels}")

    if sample_width != 2:
        pcm = audioop.lin2lin(pcm, sample_width, 2)
        sample_width = 2

    if sample_rate != 8000:
        pcm, _ = audioop.ratecv(pcm, sample_width, channels, sample_rate, 8000, None)

    return audioop.lin2ulaw(pcm, 2)


def generate_deterministic_input_audio() -> tuple[bytes, str, str]:
    """Gera fala de teste com TTS dedicado e valida a inteligibilidade com o STT real."""
    models = [SMOKE_TTS_MODEL]
    if SMOKE_TTS_MODEL != "gpt-4o-mini-tts":
        models.append("gpt-4o-mini-tts")

    response = None
    model_used = models[0]
    for index, model in enumerate(models):
        model_used = model
        response = httpx.post(
            "https://api.openai.com/v1/audio/speech",
            headers={
                "Authorization": f"Bearer {settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "voice": "marin",
                "input": SMOKE_QUESTION,
                "instructions": (
                    "Leia exatamente o texto fornecido em português do Brasil, em ritmo calmo e claro. "
                    "Pronuncie PRO como as letras P R O. Não parafraseie e não acrescente palavras."
                ),
                "response_format": "wav",
                "speed": 0.9,
            },
            timeout=60,
        )
        if response.is_success:
            break
        if index < len(models) - 1 and response.status_code in {400, 404}:
            continue
        response.raise_for_status()

    assert response is not None
    response.raise_for_status()
    mulaw = wav_to_twilio_mulaw(response.content)
    if not mulaw:
        raise RuntimeError("Endpoint Speech retornou audio vazio")

    preflight = OpenAITranscriptionClient()._transcribe_sync(mulaw)
    assert_smoke_question_transcribed(preflight.text)
    return mulaw, preflight.text, model_used


def login() -> dict[str, str]:
    r = httpx.post(
        BASE_LOCAL + "/auth/login",
        headers={"X-Tenant-Slug": TENANT},
        data={"username": "admin@example.com", "password": "ChangeMe123!"},
        timeout=20,
    )
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def api(method: str, path: str, auth: dict[str, str], **kwargs):
    r = httpx.request(method, BASE_LOCAL + path, headers=auth, timeout=45, **kwargs)
    r.raise_for_status()
    return r.json() if r.content else None


def configure_account(auth: dict[str, str]) -> dict:
    return api(
        "PUT",
        f"/channels/voice/tenant/accounts/{ACCOUNT}",
        auth,
        json={
            "account_sid": ACCOUNT_SID,
            "display_phone_number": PHONE,
            "outbound_mode": "twilio_media_stream",
            "access_token_env": AUTH_ENV,
            "is_active": True,
        },
    )


def signature_for(url: str, params: dict[str, str] | None = None) -> str:
    return RequestValidator(AUTH_TOKEN).compute_signature(url, params or {})


def signed_post(path: str, form: dict[str, str], *, valid: bool = True) -> httpx.Response:
    public_url = PUBLIC_BASE + "/api/v1" + path
    signature = signature_for(public_url, form)
    if not valid:
        signature = "invalid-signature"
    return httpx.post(
        BASE_LOCAL + path,
        data=form,
        headers={"X-Twilio-Signature": signature},
        timeout=30,
    )


def incoming_form(call_sid: str, caller: str) -> dict[str, str]:
    return {
        "AccountSid": ACCOUNT_SID,
        "CallSid": call_sid,
        "CallStatus": "ringing",
        "From": caller,
        "To": PHONE,
        "Direction": "inbound",
    }


def start_payload(*, call_sid: str, stream_sid: str, caller: str) -> dict:
    return {
        "event": "start",
        "sequenceNumber": "1",
        "streamSid": stream_sid,
        "start": {
            "accountSid": ACCOUNT_SID,
            "streamSid": stream_sid,
            "callSid": call_sid,
            "tracks": ["inbound"],
            "mediaFormat": {"encoding": "audio/x-mulaw", "sampleRate": 8000, "channels": 1},
            "customParameters": {
                "provider_account_id": ACCOUNT,
                "from_address": caller,
                "to_address": PHONE,
                "call_sid": call_sid,
            },
        },
    }


def media_payload(*, stream_sid: str, seq: int, chunk: int, raw: bytes) -> dict:
    return {
        "event": "media",
        "sequenceNumber": str(seq),
        "streamSid": stream_sid,
        "media": {
            "track": "inbound",
            "chunk": str(chunk),
            "timestamp": str(chunk * 20),
            "payload": base64.b64encode(raw).decode("ascii"),
        },
    }


def wait_session(auth: dict[str, str], call_sid: str) -> dict:
    deadline = time.time() + 30
    while time.time() < deadline:
        rows = api("GET", "/channels/voice/sessions?limit=100", auth)
        for row in rows:
            if row.get("provider_call_id") == call_sid and row.get("provider") == "twilio":
                return row
        time.sleep(0.5)
    raise RuntimeError(f"VoiceSession nao encontrada para {call_sid}")


def run_production_audio_call(*, call_sid: str, caller: str) -> tuple[dict, int, int, bool, str]:
    print("  - Gerando audio de entrada com GPT-4o Mini TTS (Speech API)...")
    prompt_audio, preflight_transcript, tts_model = generate_deterministic_input_audio()
    print("  - TTS model usado:", tts_model)
    print("  - Preflight gpt-transcribe:", preflight_transcript)

    stream_sid = "MZ" + str(random.randint(10**12, 10**13 - 1))
    local_ws = f"ws://127.0.0.1:8000/api/v1/channels/voice/twilio/media/{ACCOUNT}"
    external_ws = WSS_BASE + f"/api/v1/channels/voice/twilio/media/{ACCOUNT}"
    ws_sig = signature_for(external_ws, {})
    ws = websocket.create_connection(
        local_ws,
        header=[f"X-Twilio-Signature: {ws_sig}"],
        timeout=100,
    )
    outbound_frames = 0
    outbound_bytes = 0
    saw_mark = False
    try:
        ws.send(json.dumps({"event": "connected", "protocol": "Call", "version": "1.0.0"}))
        ws.send(json.dumps(start_payload(call_sid=call_sid, stream_sid=stream_sid, caller=caller)))
        seq = 2
        chunk = 1
        for frame in iter_mulaw_frames(prompt_audio):
            if len(frame) < TWILIO_MEDIA_FRAME_BYTES:
                frame = frame + (b"\xff" * (TWILIO_MEDIA_FRAME_BYTES - len(frame)))
            ws.send(json.dumps(media_payload(stream_sid=stream_sid, seq=seq, chunk=chunk, raw=frame)))
            seq += 1
            chunk += 1
        # 800 ms de silencio para fechar o turno no VAD local (40 x 20 ms).
        for _ in range(40):
            ws.send(json.dumps(media_payload(
                stream_sid=stream_sid,
                seq=seq,
                chunk=chunk,
                raw=b"\xff" * TWILIO_MEDIA_FRAME_BYTES,
            )))
            seq += 1
            chunk += 1

        deadline = time.time() + 90
        while time.time() < deadline:
            raw = ws.recv()
            if not raw:
                break
            msg = json.loads(raw)
            if msg.get("event") == "media":
                audio = base64.b64decode(msg["media"]["payload"])
                outbound_frames += 1
                outbound_bytes += len(audio)
            elif msg.get("event") == "mark":
                saw_mark = True
                ws.send(json.dumps({
                    "event": "mark",
                    "sequenceNumber": str(seq),
                    "streamSid": stream_sid,
                    "mark": {"name": msg.get("mark", {}).get("name", "done")},
                }))
                break
        ws.send(json.dumps({
            "event": "stop",
            "sequenceNumber": str(seq + 1),
            "streamSid": stream_sid,
            "stop": {"accountSid": ACCOUNT_SID, "callSid": call_sid},
        }))
        time.sleep(0.5)
    finally:
        try:
            ws.close()
        except Exception:
            pass
    return {"stream_sid": stream_sid, "tts_model": tts_model}, outbound_frames, outbound_bytes, saw_mark, preflight_transcript


def unsigned_ws_is_rejected() -> bool:
    local_ws = f"ws://127.0.0.1:8000/api/v1/channels/voice/twilio/media/{ACCOUNT}"
    try:
        ws = websocket.create_connection(local_ws, timeout=10)
    except Exception:
        return True
    else:
        try:
            ws.close()
        except Exception:
            pass
        return False


def main() -> int:
    print("=== AI Sales Agent Platform v0.11.1 - Production Telephony Hardening Smoke Test ===")
    auth = login()

    print("\n[1/8] Configuracao Voice e conta Twilio de producao simulada...")
    config = api("GET", "/channels/voice/config", auth)
    account = configure_account(auth)
    readiness = api("GET", f"/channels/voice/tenant/accounts/{ACCOUNT}/production-readiness", auth)
    print(json.dumps(config, indent=2, ensure_ascii=False))
    print(json.dumps(account, indent=2, ensure_ascii=False))
    print(json.dumps(readiness, indent=2, ensure_ascii=False))
    assert readiness["ready_for_twilio_configuration"] is True
    assert config["twilio_media_streams"]["production_transcript_injection"] is False

    print("\n[2/8] Webhook inbound: assinatura invalida=403 e assinatura valida=TwiML de producao...")
    suffix = str(int(time.time() * 1000))
    call_sid = "CA.v11.prod." + suffix
    caller = "+55119" + str(random.randint(10000000, 99999999))
    form = incoming_form(call_sid, caller)
    bad = signed_post(f"/channels/voice/twilio/incoming/{ACCOUNT}", form, valid=False)
    assert bad.status_code == 403, bad.text
    good = signed_post(f"/channels/voice/twilio/incoming/{ACCOUNT}", form, valid=True)
    good.raise_for_status()
    print(good.text)
    assert f"wss://voice.example.test/api/v1/channels/voice/twilio/media/{ACCOUNT}" in good.text
    assert "statusCallback=" in good.text
    assert "lab_transcript" not in good.text

    print("\n[3/8] Call status callbacks assinados e idempotentes...")
    for status in ("ringing", "in-progress"):
        payload = {
            "AccountSid": ACCOUNT_SID,
            "CallSid": call_sid,
            "CallStatus": status,
            "From": caller,
            "To": PHONE,
        }
        r = signed_post(f"/channels/voice/twilio/call-status/{ACCOUNT}", payload)
        r.raise_for_status()
        print(r.json())
    replay = signed_post(f"/channels/voice/twilio/call-status/{ACCOUNT}", {
        "AccountSid": ACCOUNT_SID,
        "CallSid": call_sid,
        "CallStatus": "ringing",
        "From": caller,
        "To": PHONE,
    })
    replay.raise_for_status()
    assert replay.json()["duplicate"] is True

    print("\n[4/8] Stream status callback assinado...")
    stream_status = {
        "AccountSid": ACCOUNT_SID,
        "CallSid": call_sid,
        "StreamSid": "MZ.v11." + suffix,
        "StreamName": "ai-sales-agent",
        "StreamEvent": "stream-started",
        "Timestamp": "2026-09-07T20:00:00Z",
    }
    sr = signed_post(f"/channels/voice/twilio/stream-status/{ACCOUNT}", stream_status)
    sr.raise_for_status()
    print(sr.json())

    print("\n[5/8] Handshake WSS sem X-Twilio-Signature deve ser rejeitado...")
    assert unsigned_ws_is_rejected() is True
    print("[OK] WebSocket nao assinado rejeitado")

    print("\n[6/8] Audio real PCMU -> VAD -> gpt-transcribe -> LangGraph/tools -> Realtime PCMU...")
    stream_info, out_frames, out_bytes, saw_mark, preflight_transcript = run_production_audio_call(
        call_sid=call_sid, caller=caller
    )
    print(json.dumps({
        "call_sid": call_sid,
        "caller": caller,
        "stream_sid": stream_info["stream_sid"],
        "tts_model": stream_info["tts_model"],
        "preflight_transcript": preflight_transcript,
        "outbound_frames": out_frames,
        "outbound_bytes": out_bytes,
        "saw_mark": saw_mark,
    }, indent=2, ensure_ascii=False))
    assert out_frames > 0 and out_bytes > 0 and saw_mark

    print("\n[7/8] Sessao persistida confirma STT de producao e preco do tenant...")
    session = wait_session(auth, call_sid)
    print(json.dumps(session, indent=2, ensure_ascii=False))
    bridge = (session.get("session_metadata") or {}).get("twilio_bridge") or {}
    assert session.get("input_transcript")
    assert_smoke_question_transcribed(str(session.get("input_transcript") or ""))
    assert "997" in (session.get("assistant_text") or "")
    assert bridge.get("mode") == "production"
    assert int(bridge.get("transcription_turns") or 0) >= 1
    assert int(bridge.get("transcription_audio_bytes") or 0) > 0
    assert bridge.get("last_transcript")

    print("\n[8/8] Call completed + auditoria de ChannelEvents Voice...")
    completed = {
        "AccountSid": ACCOUNT_SID,
        "CallSid": call_sid,
        "CallStatus": "completed",
        "CallDuration": "42",
        "From": caller,
        "To": PHONE,
    }
    cr = signed_post(f"/channels/voice/twilio/call-status/{ACCOUNT}", completed)
    cr.raise_for_status()
    events = api("GET", "/channels/voice/channel-events?limit=100", auth)
    relevant = [e for e in events if call_sid in e.get("provider_event_id", "") or (e.get("event_metadata") or {}).get("CallSid") == call_sid]
    print(json.dumps(relevant, indent=2, ensure_ascii=False))
    assert any(e.get("event_type") == "incoming_call" for e in relevant)
    assert any(e.get("event_type") == "call_status" and e.get("status") == "completed" for e in relevant)
    assert any(e.get("event_type") == "stream_status" for e in relevant)

    print("\n=== v0.11.1 VALIDADA COM SUCESSO ===")
    print("Call ID              :", call_sid)
    print("TTS model            :", stream_info["tts_model"])
    print("Preflight transcript :", preflight_transcript)
    print("Input transcript     :", session.get("input_transcript"))
    print("Business text        :", session.get("assistant_text"))
    print("STT model            :", bridge.get("transcribe_model"))
    print("Outbound PCMU        :", out_frames, "frames /", out_bytes, "bytes")
    print("Signature HTTP       : validated")
    print("Signature WSS        : validated")
    print("Unsigned WSS         : rejected")
    print("PSTN connected       : false (assinaturas e audio testados localmente)")
    print("Production first turn: true")
    print("Swagger              : http://localhost:8000/docs")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print("v0.11 smoke test failed:", repr(exc), file=sys.stderr)
        raise
