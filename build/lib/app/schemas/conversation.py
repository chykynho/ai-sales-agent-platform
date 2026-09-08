import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict
from app.models.conversation import Channel


class ConversationCreate(BaseModel):
    customer_id: uuid.UUID
    channel: Channel = Channel.WEB


class ConversationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    tenant_id: uuid.UUID
    customer_id: uuid.UUID
    channel: Channel
    status: str
    created_at: datetime
