from __future__ import annotations

import base64
import json
import random
import sys
import time
from dataclasses import dataclass

import httpx
import websocket

BASE = "http://127.0.0.1:8000/api/v1"
WS_URL = "ws://127.0.0.1:8000/api/v1/channels/voice/twilio/media"
TENANT = "demo"
ACCOUNT = "smoke-twilio-demo-001"
LAB_TOKEN = "local-v10-bridge-token-change-me"


@dataclass
class CallResult:
    call_sid: str
    caller: str
    stream_sid: str
    outbound_frames: int
    outbound_bytes: int
    saw_mark: bool
    saw_clear: bool


def login() -> dict[str, str]:
    r = httpx.post(
        BASE + "/auth/login",
        headers={"X-Tenant-Slug": TENANT},
        data={"username": "admin@example.com", "password": "ChangeMe123!"},
        timeout=20,
    )
    r.raise_for_status()
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def api(method: str, path: str, auth: dict[str, str], **kwargs):
    r = httpx.request(method, BASE + path, headers=auth, timeout=30, **kwargs)
    r.raise_for_status()
    return r.json() if r.content else None


def configure_account(auth: dict[str, str]) -> None:
    api(
        "PUT",
        f"/channels/voice/tenant/accounts/{ACCOUNT}",
        auth,
        json={
            "account_sid": "ACSMOKEDEMO",
            "display_phone_number": "+5511000000000",
            "outbound_mode": "mock",
            "is_active": True,
        },
    )


def start_payload(*, call_sid: str, stream_sid: str, caller: str) -> dict:
    return {
        "event": "start",
        "sequenceNumber": "1",
        "streamSid": stream_sid,
        "start": {
            "accountSid": "ACSMOKEDEMO",
            "streamSid": stream_sid,
            "callSid": call_sid,
            "tracks": ["inbound"],
            "mediaFormat": {"encoding": "audio/x-mulaw", "sampleRate": 8000, "channels": 1},
            "customParameters": {
                "provider_account_id": ACCOUNT,
                "lab_token": LAB_TOKEN,
                "from_address": caller,
                "lab_transcript": "Quanto custa o Plano PRO? Use a fonte correta.",
            },
        },
    }


def media_payload(*, stream_sid: str, seq: int, chunk: int, raw: bytes | None = None) -> dict:
    raw = raw or (b"\xff" * 160)
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


def run_call(*, barge_in: bool) -> CallResult:
    suffix = f"{int(time.time()*1000)}{random.randint(100,999)}"
    call_sid = ("CA.v10.barge." if barge_in else "CA.v10.normal.") + suffix
    stream_sid = "MZ" + suffix
    caller = "55119" + str(random.randint(10000000, 99999999))
    ws = websocket.create_connection(WS_URL, timeout=75)
    outbound_frames = 0
    outbound_bytes = 0
    saw_mark = False
    saw_clear = False
    try:
        ws.send(json.dumps({"event": "connected", "protocol": "Call", "version": "1.0.0"}))
        ws.send(json.dumps(start_payload(call_sid=call_sid, stream_sid=stream_sid, caller=caller)))
        for idx in range(1, 5):
            ws.send(json.dumps(media_payload(stream_sid=stream_sid, seq=idx+1, chunk=idx)))

        barge_sent = False
        deadline = time.time() + 70
        while time.time() < deadline:
            raw = ws.recv()
            if not raw:
                break
            msg = json.loads(raw)
            typ = msg.get("event")
            if typ == "media":
                audio = base64.b64decode(msg["media"]["payload"])
                outbound_frames += 1
                outbound_bytes += len(audio)
                if barge_in and not barge_sent:
                    barge_sent = True
                    ws.send(json.dumps(media_payload(stream_sid=stream_sid, seq=99, chunk=99)))
            elif typ == "clear":
                saw_clear = True
                if barge_in:
                    break
            elif typ == "mark":
                saw_mark = True
                ws.send(json.dumps({
                    "event": "mark",
                    "sequenceNumber": "100",
                    "streamSid": stream_sid,
                    "mark": {"name": msg.get("mark", {}).get("name", "done")},
                }))
                if not barge_in:
                    break
        ws.send(json.dumps({
            "event": "stop",
            "sequenceNumber": "101",
            "streamSid": stream_sid,
            "stop": {"accountSid": "ACSMOKEDEMO", "callSid": call_sid},
        }))
        time.sleep(0.4)
    finally:
        try:
            ws.close()
        except Exception:
            pass
    return CallResult(call_sid, caller, stream_sid, outbound_frames, outbound_bytes, saw_mark, saw_clear)


def find_session(auth: dict[str, str], call_sid: str) -> dict:
    deadline = time.time() + 20
    while time.time() < deadline:
        sessions = api("GET", "/channels/voice/sessions?limit=100", auth)
        for row in sessions:
            if row.get("provider_call_id") == call_sid and row.get("provider") == "twilio":
                bridge = (row.get("session_metadata") or {}).get("twilio_bridge")
                if bridge:
                    return row
        time.sleep(0.5)
    raise RuntimeError(f"voice session/bridge summary not found for {call_sid}")


def main() -> int:
    print("=== AI Sales Agent Platform v0.10 - Twilio Media Streams Bridge Smoke Test ===")
    auth = login()

    print("\n[1/7] Voice bridge config and tenant account...")
    config = api("GET", "/channels/voice/config", auth)
    configure_account(auth)
    bridge_cfg = config["twilio_media_streams"]
    print(json.dumps(bridge_cfg, indent=2, ensure_ascii=False))
    assert bridge_cfg["live_audio_bridge"] == "v0.10_lab"
    assert bridge_cfg["barge_in"] is True
    assert bridge_cfg["production_pstn_connected"] is False

    print("\n[2/7] Normal bidirectional stream: inbound media -> LangGraph/tools -> Realtime PCMU -> Twilio media...")
    normal = run_call(barge_in=False)
    print(json.dumps(normal.__dict__, indent=2))
    assert normal.outbound_frames > 0 and normal.outbound_bytes > 0
    assert normal.saw_mark and not normal.saw_clear

    print("\n[3/7] Persisted normal bridge metrics...")
    normal_session = find_session(auth, normal.call_sid)
    normal_bridge = normal_session["session_metadata"]["twilio_bridge"]
    print(json.dumps(normal_session, indent=2, ensure_ascii=False))
    assert "997" in (normal_session.get("assistant_text") or "")
    assert int(normal_bridge["inbound_frames"]) >= 4
    assert int(normal_bridge["outbound_frames"]) > 0
    assert int(normal_bridge["marks_sent"]) >= 1
    assert int(normal_bridge["barge_in_count"]) == 0

    print("\n[4/7] Barge-in stream: caller speaks while assistant audio is playing...")
    barged = run_call(barge_in=True)
    print(json.dumps(barged.__dict__, indent=2))
    assert barged.outbound_frames >= 1
    assert barged.saw_clear

    print("\n[5/7] Persisted barge-in metrics...")
    barge_session = find_session(auth, barged.call_sid)
    barge_bridge = barge_session["session_metadata"]["twilio_bridge"]
    print(json.dumps(barge_session, indent=2, ensure_ascii=False))
    assert int(barge_bridge["barge_in_count"]) >= 1
    assert int(barge_bridge["clears_sent"]) >= 1
    assert barge_bridge["interrupted"] is True
    assert int(barge_bridge["outbound_bytes"]) < int(barge_session["audio_bytes"])

    print("\n[6/7] LangGraph state remains tenant-scoped for the normal call...")
    state = api("GET", f"/agent/threads/{normal_session['external_thread_id']}/state", auth)
    print(json.dumps(state, indent=2, ensure_ascii=False))
    assert "997" in (state.get("final_output") or "")
    assert int(state.get("message_count") or 0) >= 2

    print("\n[7/7] Voice events contain Realtime audio + Twilio stream audit...")
    events = api("GET", f"/channels/voice/sessions/{normal_session['id']}/events", auth)
    print(json.dumps(events, indent=2, ensure_ascii=False))
    assert any(e.get("event_type") == "realtime_audio" and int(e.get("audio_bytes") or 0) > 0 for e in events)
    assert any(e.get("event_type") == "twilio_media_stream" for e in events)

    print("\n=== v0.10 VALIDADA COM SUCESSO ===")
    print("Normal Call ID    :", normal.call_sid)
    print("Normal media      :", normal.outbound_frames, "frames /", normal.outbound_bytes, "bytes")
    print("Normal mark       : validated")
    print("Barge-in Call ID  :", barged.call_sid)
    print("Barge-in clear    : validated")
    print("Barge-in count    :", barge_bridge["barge_in_count"])
    print("Business text     :", normal_session.get("assistant_text"))
    print("Realtime model    :", normal_session.get("realtime_model"))
    print("PSTN connected    : false (Twilio-compatible lab client)")
    print("Swagger           : http://localhost:8000/docs")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print("v0.10 smoke test failed:", repr(exc), file=sys.stderr)
        raise
