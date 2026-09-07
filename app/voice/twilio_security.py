from __future__ import annotations

import os
from urllib.parse import urlsplit, urlunsplit

from fastapi import Request, WebSocket
from twilio.request_validator import RequestValidator

from app.core.config import settings
from app.models.channel import ChannelAccount


class TwilioSecurityError(RuntimeError):
    pass


def _secret_for_account(account: ChannelAccount) -> str:
    env_name = str(account.access_token_env or "").strip()
    if not env_name:
        raise TwilioSecurityError("Conta Twilio sem access_token_env configurado")
    token = os.environ.get(env_name)
    if not token:
        raise TwilioSecurityError(f"Variavel de ambiente Twilio ausente: {env_name}")
    return token


def _external_url(base_url: str | None, path: str, query: str = "") -> str:
    if not base_url:
        raise TwilioSecurityError("URL publica Twilio nao configurada")
    base = urlsplit(base_url)
    if not base.scheme or not base.netloc:
        raise TwilioSecurityError("URL publica Twilio invalida")
    base_path = base.path.rstrip("/")
    full_path = base_path + (path if path.startswith("/") else "/" + path)
    return urlunsplit((base.scheme, base.netloc, full_path, query, ""))


def external_http_url(request: Request) -> str:
    return _external_url(settings.twilio_public_base_url, request.url.path, request.url.query)


def external_websocket_url(websocket: WebSocket) -> str:
    return _external_url(settings.twilio_wss_base_url, websocket.url.path, websocket.url.query)


def validate_http_signature(*, request: Request, account: ChannelAccount, form: dict[str, str]) -> bool:
    if not settings.twilio_require_signature:
        return True
    signature = str(request.headers.get("X-Twilio-Signature") or "")
    if not signature:
        return False
    token = _secret_for_account(account)
    return bool(RequestValidator(token).validate(external_http_url(request), form, signature))


def validate_websocket_signature(*, websocket: WebSocket, account: ChannelAccount) -> bool:
    if not settings.twilio_require_signature:
        return True
    signature = str(websocket.headers.get("X-Twilio-Signature") or "")
    if not signature:
        return False
    token = _secret_for_account(account)
    validator = RequestValidator(token)
    url = external_websocket_url(websocket)
    if validator.validate(url, {}, signature):
        return True
    # A documentacao da Twilio recomenda tentar a barra final em handshakes WSS
    # quando a verificacao de assinatura falha por normalizacao de URL.
    if not url.endswith("/") and validator.validate(url + "/", {}, signature):
        return True
    return False
