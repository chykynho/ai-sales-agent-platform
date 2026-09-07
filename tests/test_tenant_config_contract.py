from decimal import Decimal
import pytest
from pydantic import ValidationError
from app.schemas.tenant_config import BusinessHours, TenantConfigUpdate
from app.tools.registry import get_tool_registry


def test_registry_can_be_filtered_per_tenant():
    filtered = get_tool_registry().filtered(["check_price", "create_lead"])
    assert filtered.names() == ["check_price", "create_lead"]


def test_unknown_tool_is_rejected():
    with pytest.raises(ValidationError):
        TenantConfigUpdate(enabled_tools=["check_price", "delete_everything"])


def test_business_hours_are_validated():
    assert BusinessHours(weekdays=[0,1,2,3,4], start="09:00", end="17:00").end == "17:00"
    with pytest.raises(ValidationError):
        BusinessHours(weekdays=[7], start="09:00", end="17:00")


def test_rag_similarity_range():
    value = TenantConfigUpdate(rag_min_similarity=Decimal("0.35"))
    assert value.rag_min_similarity == Decimal("0.35")
