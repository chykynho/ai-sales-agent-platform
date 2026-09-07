from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Any

from opentelemetry import trace

_request_id: ContextVar[str] = ContextVar("request_id", default="")
_tenant_id: ContextVar[str] = ContextVar("tenant_id", default="")
_conversation_id: ContextVar[str] = ContextVar("conversation_id", default="")
_call_sid: ContextVar[str] = ContextVar("call_sid", default="")


@dataclass(slots=True)
class ContextTokens:
    request_id: Token[str] | None = None
    tenant_id: Token[str] | None = None
    conversation_id: Token[str] | None = None
    call_sid: Token[str] | None = None


def bind_context(
    *,
    request_id: str | None = None,
    tenant_id: str | None = None,
    conversation_id: str | None = None,
    call_sid: str | None = None,
) -> ContextTokens:
    tokens = ContextTokens()
    if request_id is not None:
        tokens.request_id = _request_id.set(str(request_id))
    if tenant_id is not None:
        tokens.tenant_id = _tenant_id.set(str(tenant_id))
    if conversation_id is not None:
        tokens.conversation_id = _conversation_id.set(str(conversation_id))
    if call_sid is not None:
        tokens.call_sid = _call_sid.set(str(call_sid))
    return tokens


def reset_context(tokens: ContextTokens) -> None:
    if tokens.call_sid is not None:
        _call_sid.reset(tokens.call_sid)
    if tokens.conversation_id is not None:
        _conversation_id.reset(tokens.conversation_id)
    if tokens.tenant_id is not None:
        _tenant_id.reset(tokens.tenant_id)
    if tokens.request_id is not None:
        _request_id.reset(tokens.request_id)


def clear_context() -> None:
    _request_id.set("")
    _tenant_id.set("")
    _conversation_id.set("")
    _call_sid.set("")


def request_id() -> str:
    return _request_id.get()


def tenant_id() -> str:
    return _tenant_id.get()


def conversation_id() -> str:
    return _conversation_id.get()


def call_sid() -> str:
    return _call_sid.get()


def trace_ids() -> tuple[str, str]:
    span = trace.get_current_span()
    ctx = span.get_span_context()
    if not ctx.is_valid:
        return "", ""
    return f"{ctx.trace_id:032x}", f"{ctx.span_id:016x}"


def snapshot() -> dict[str, Any]:
    trace_id, span_id = trace_ids()
    return {
        "request_id": request_id(),
        "tenant_id": tenant_id(),
        "conversation_id": conversation_id(),
        "call_sid": call_sid(),
        "trace_id": trace_id,
        "span_id": span_id,
    }
