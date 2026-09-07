import hashlib
import hmac

from app.core.config import settings
from app.channels.whatsapp_protocol import extract_text_messages, verify_signature


def test_signature_validation():
    body = b'{"object":"whatsapp_business_account"}'
    digest = hmac.new(settings.whatsapp_app_secret.encode(), body, hashlib.sha256).hexdigest()
    assert verify_signature(raw_body=body, signature_header=f"sha256={digest}")
    assert not verify_signature(raw_body=body, signature_header="sha256=bad")


def test_extract_text_message_contract():
    payload = {
        "entry": [{"changes": [{"value": {
            "metadata": {"phone_number_id": "p1", "display_phone_number": "5511"},
            "contacts": [{"wa_id": "551199", "profile": {"name": "Maria"}}],
            "messages": [{"id": "wamid.1", "from": "551199", "type": "text", "text": {"body": "Oi"}}],
        }}]}]
    }
    result = extract_text_messages(payload)
    assert result == [{
        "phone_number_id": "p1",
        "display_phone_number": "5511",
        "provider_event_id": "wamid.1",
        "from": "551199",
        "profile_name": "Maria",
        "text": "Oi",
    }]
