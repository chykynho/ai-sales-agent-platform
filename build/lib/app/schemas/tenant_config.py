from __future__ import annotations

import uuid
from decimal import Decimal
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.tenant_defaults import KNOWN_TOOL_NAMES


class BusinessHours(BaseModel):
    weekdays: list[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4], min_length=1, max_length=7)
    start: str = Field(default="09:00", pattern=r"^\d{2}:\d{2}$")
    end: str = Field(default="17:00", pattern=r"^\d{2}:\d{2}$")

    @field_validator("start", "end")
    @classmethod
    def validate_time(cls, value: str) -> str:
        hour, minute = (int(x) for x in value.split(":"))
        if hour > 23 or minute > 59:
            raise ValueError("business hour must be a valid HH:MM time")
        return value

    @field_validator("weekdays")
    @classmethod
    def validate_weekdays(cls, value: list[int]) -> list[int]:
        if any(day < 0 or day > 6 for day in value):
            raise ValueError("weekdays must contain integers from 0 (Monday) through 6 (Sunday)")
        if len(set(value)) != len(value):
            raise ValueError("weekdays cannot contain duplicates")
        return value

    @model_validator(mode="after")
    def validate_window(self):
        if self.start >= self.end:
            raise ValueError("business_hours.start must be earlier than business_hours.end")
        return self


class TenantConfigRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    tenant_id: uuid.UUID
    company_name: str
    assistant_name: str
    locale: str
    timezone: str
    tone: str
    custom_instructions: str
    enabled_tools: list[str]
    business_hours: dict
    rag_top_k: int
    rag_min_similarity: Decimal
    config_version: int
    created_at: datetime
    updated_at: datetime


class TenantConfigUpdate(BaseModel):
    company_name: str | None = Field(default=None, min_length=1, max_length=200)
    assistant_name: str | None = Field(default=None, min_length=1, max_length=100)
    locale: str | None = Field(default=None, min_length=2, max_length=20)
    timezone: str | None = Field(default=None, min_length=1, max_length=100)
    tone: str | None = Field(default=None, min_length=1, max_length=50)
    custom_instructions: str | None = Field(default=None, max_length=5000)
    enabled_tools: list[str] | None = None
    business_hours: BusinessHours | None = None
    rag_top_k: int | None = Field(default=None, ge=1, le=20)
    rag_min_similarity: Decimal | None = Field(default=None, ge=Decimal("-1"), le=Decimal("1"))

    @field_validator("enabled_tools")
    @classmethod
    def validate_tools(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return value
        unknown = sorted(set(value) - set(KNOWN_TOOL_NAMES))
        if unknown:
            raise ValueError(f"Unknown tools: {', '.join(unknown)}")
        return list(dict.fromkeys(value))


class TenantProductRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    tenant_id: uuid.UUID
    code: str
    name: str
    description: str | None
    currency: str
    price: Decimal
    is_active: bool
    created_at: datetime
    updated_at: datetime


class TenantProductUpsert(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    currency: str = Field(default="BRL", min_length=3, max_length=3)
    price: Decimal = Field(gt=Decimal("0"), max_digits=12, decimal_places=2)
    is_active: bool = True
