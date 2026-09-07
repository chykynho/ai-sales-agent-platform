from __future__ import annotations

from typing import Mapping

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.channel import ChannelAccount, ChannelEvent
from app.models.voice import VoiceSession


class TwilioVoiceService:
    async def get_account(self, *, db: AsyncSession, provider_account_id: str) -> ChannelAccount | None:
        return (
            await db.execute(
                select(ChannelAccount).where(
                    ChannelAccount.channel == "voice",
                    ChannelAccount.provider == "twilio",
                    ChannelAccount.provider_account_id == provider_account_id,
                    ChannelAccount.is_active.is_(True),
                )
            )
        ).scalar_one_or_none()

    @staticmethod
    def ensure_account_sid(account: ChannelAccount, account_sid: str) -> None:
        configured = str(account.business_account_id or "").strip()
        received = str(account_sid or "").strip()
        if not configured:
            raise ValueError("Conta Twilio sem AccountSid configurado")
        if not received:
            raise ValueError("AccountSid ausente na requisicao Twilio")
        if configured != received:
            raise ValueError("AccountSid nao corresponde a conta Twilio configurada")

    async def record_channel_event(
        self,
        *,
        db: AsyncSession,
        account: ChannelAccount,
        provider_event_id: str,
        event_type: str,
        status: str,
        direction: str,
        form: Mapping[str, str],
    ) -> tuple[ChannelEvent, bool]:
        existing = (
            await db.execute(
                select(ChannelEvent).where(
                    ChannelEvent.provider == "twilio",
                    ChannelEvent.provider_event_id == provider_event_id,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing, True

        event = ChannelEvent(
            tenant_id=account.tenant_id,
            channel_account_id=account.id,
            provider="twilio",
            channel="voice",
            provider_event_id=provider_event_id,
            direction=direction,
            event_type=event_type,
            status=status[:30] or "accepted",
            from_address=form.get("From") or form.get("Caller"),
            to_address=form.get("To") or form.get("Called") or account.display_phone_number,
            event_metadata=dict(form),
        )
        db.add(event)
        await db.commit()
        await db.refresh(event)
        return event, False

    async def annotate_voice_session(
        self,
        *,
        db: AsyncSession,
        account: ChannelAccount,
        call_sid: str,
        namespace: str,
        payload: dict,
    ) -> None:
        if not call_sid:
            return
        session = (
            await db.execute(
                select(VoiceSession).where(
                    VoiceSession.tenant_id == account.tenant_id,
                    VoiceSession.channel_account_id == account.id,
                    VoiceSession.provider == "twilio",
                    VoiceSession.provider_call_id == call_sid,
                )
            )
        ).scalar_one_or_none()
        if session is None:
            return
        metadata = dict(session.session_metadata or {})
        history = list(metadata.get(namespace) or [])
        history.append(payload)
        metadata[namespace] = history[-20:]
        session.session_metadata = metadata
        await db.commit()
