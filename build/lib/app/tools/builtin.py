from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import select

from app.models.customer import Customer
from app.models.lead import Lead
from app.models.tenant_config import TenantProduct
from app.services.knowledge_service import KnowledgeService
from app.tools.exceptions import ToolExecutionError
from app.tools.types import ToolContext


class StrictArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CheckPriceArgs(StrictArgs):
    product_code: str = Field(min_length=1, max_length=50, description="Product code such as STARTER or PRO")


class GetCustomerByEmailArgs(StrictArgs):
    email: EmailStr


class CheckAvailabilityArgs(StrictArgs):
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$", description="Date in YYYY-MM-DD")
    time: str = Field(pattern=r"^\d{2}:\d{2}$", description="Time in HH:MM, 24-hour clock")


class CreateLeadArgs(StrictArgs):
    name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    interest: str = Field(min_length=1, max_length=1000)


class SearchKnowledgeArgs(StrictArgs):
    query: str = Field(min_length=2, max_length=2000, description="Pergunta para buscar na base de conhecimento do tenant atual")


async def check_price(ctx: ToolContext, args: CheckPriceArgs) -> dict:
    code = args.product_code.strip().upper()
    item = (await ctx.db.execute(select(TenantProduct).where(
        TenantProduct.tenant_id == ctx.current_user.tenant_id,
        TenantProduct.code == code,
        TenantProduct.is_active.is_(True),
    ))).scalar_one_or_none()
    if item is None:
        return {"found": False, "product_code": code}
    return {
        "found": True,
        "product_code": code,
        "product_name": item.name,
        "currency": item.currency,
        "price": str(item.price),
        "price_brl": str(item.price) if item.currency == "BRL" else None,
    }


async def get_customer_by_email(ctx: ToolContext, args: GetCustomerByEmailArgs) -> dict:
    result = await ctx.db.execute(select(Customer).where(
        Customer.tenant_id == ctx.current_user.tenant_id,
        Customer.email == str(args.email),
    ))
    customer = result.scalar_one_or_none()
    if customer is None:
        return {"found": False, "email": str(args.email)}
    return {"found": True, "customer_id": str(customer.id), "name": customer.name, "email": customer.email, "phone": customer.phone}


async def check_availability(ctx: ToolContext, args: CheckAvailabilityArgs) -> dict:
    try:
        dt = datetime.fromisoformat(f"{args.date}T{args.time}:00")
    except ValueError:
        return {"available": False, "reason": "invalid_datetime"}
    config = ctx.tenant_config
    hours = getattr(config, "business_hours", None) or {"weekdays": [0,1,2,3,4], "start": "09:00", "end": "17:00"}
    weekdays = set(int(x) for x in hours.get("weekdays", [0,1,2,3,4]))
    start = str(hours.get("start", "09:00"))
    end = str(hours.get("end", "17:00"))
    current = args.time
    available = dt.weekday() in weekdays and start <= current < end
    return {
        "available": available,
        "date": args.date,
        "time": args.time,
        "timezone": getattr(config, "timezone", "America/Sao_Paulo"),
        "business_hours": {"weekdays": sorted(weekdays), "start": start, "end": end},
        "reason": None if available else "outside_business_hours",
    }


async def search_knowledge(ctx: ToolContext, args: SearchKnowledgeArgs) -> dict:
    _embedding, sources = await KnowledgeService().search(
        db=ctx.db,
        current_user=ctx.current_user,
        query=args.query,
        top_k=None,
        tenant_config=ctx.tenant_config,
    )
    return {
        "found": bool(sources),
        "sources": [
            {"source_id": f"S{source.rank}", "filename": source.filename, "version": source.version, "page_number": source.page_number, "similarity": source.similarity, "content": source.content}
            for source in sources
        ],
    }


async def create_lead(ctx: ToolContext, args: CreateLeadArgs) -> dict:
    existing = await ctx.db.execute(select(Lead).where(
        Lead.tenant_id == ctx.current_user.tenant_id,
        Lead.idempotency_key == ctx.idempotency_key,
    ))
    lead = existing.scalar_one_or_none()
    if lead is not None:
        if lead.request_hash != ctx.arguments_hash:
            raise ToolExecutionError("Idempotency-Key was already used with a different create_lead payload", code="idempotency_conflict")
        return {"created": False, "idempotent_replay": True, "lead_id": str(lead.id), "status": lead.status}

    lead = Lead(
        tenant_id=ctx.current_user.tenant_id,
        name=args.name,
        email=str(args.email),
        interest=args.interest,
        status="new",
        source="ai_agent",
        idempotency_key=ctx.idempotency_key,
        request_hash=ctx.arguments_hash,
    )
    ctx.db.add(lead)
    await ctx.db.flush()
    return {"created": True, "idempotent_replay": False, "lead_id": str(lead.id), "status": lead.status}
