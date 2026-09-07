import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict
from app.models.message import MessageRole


class MessageCreate(BaseModel):
    role: MessageRole = MessageRole.USER
    content: str


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    tenant_id: uuid.UUID
    conversation_id: uuid.UUID
    role: MessageRole
    content: str
    created_at: datetime
