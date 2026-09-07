from typing import Annotated
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser
from app.db.session import get_db
from app.models.conversation import Conversation
from app.models.customer import Customer
from app.models.message import Message
from app.schemas.conversation import ConversationCreate, ConversationRead
from app.schemas.message import MessageCreate, MessageRead

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.post("", response_model=ConversationRead, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    payload: ConversationCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Conversation:
    customer_result = await db.execute(
        select(Customer).where(
            Customer.id == payload.customer_id,
            Customer.tenant_id == current_user.tenant_id,
        )
    )
    if customer_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Customer not found")

    conversation = Conversation(tenant_id=current_user.tenant_id, **payload.model_dump())
    db.add(conversation)
    await db.commit()
    await db.refresh(conversation)
    return conversation


@router.get("", response_model=list[ConversationRead])
async def list_conversations(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[Conversation]:
    result = await db.execute(
        select(Conversation)
        .where(Conversation.tenant_id == current_user.tenant_id)
        .order_by(Conversation.created_at.desc())
    )
    return list(result.scalars().all())


@router.post("/{conversation_id}/messages", response_model=MessageRead, status_code=201)
async def create_message(
    conversation_id: uuid.UUID,
    payload: MessageCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Message:
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.tenant_id == current_user.tenant_id,
        )
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    message = Message(
        tenant_id=current_user.tenant_id,
        conversation_id=conversation_id,
        **payload.model_dump(),
    )
    db.add(message)
    await db.commit()
    await db.refresh(message)
    return message


@router.get("/{conversation_id}/messages", response_model=list[MessageRead])
async def list_messages(
    conversation_id: uuid.UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[Message]:
    conversation_result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.tenant_id == current_user.tenant_id,
        )
    )
    if conversation_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    result = await db.execute(
        select(Message)
        .where(
            Message.conversation_id == conversation_id,
            Message.tenant_id == current_user.tenant_id,
        )
        .order_by(Message.created_at.asc())
    )
    return list(result.scalars().all())
