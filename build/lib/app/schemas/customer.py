import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict, EmailStr


class CustomerCreate(BaseModel):
    external_id: str | None = None
    name: str
    email: EmailStr | None = None
    phone: str | None = None


class CustomerRead(CustomerCreate):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    tenant_id: uuid.UUID
    created_at: datetime
