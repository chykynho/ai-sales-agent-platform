from decimal import Decimal

from app.llm.pricing import estimate_openai_cost
from app.llm.types import TokenUsage


def test_terra_cost_estimate() -> None:
    usage = TokenUsage(input_tokens=1_000_000, output_tokens=1_000_000)
    estimate = estimate_openai_cost("gpt-5.6-terra", usage)
    assert estimate is not None
    assert estimate.total_usd == Decimal("14.00000000")


def test_cached_tokens_not_double_counted() -> None:
    usage = TokenUsage(input_tokens=1_000_000, cached_input_tokens=500_000, output_tokens=0)
    estimate = estimate_openai_cost("gpt-5.6-terra", usage)
    assert estimate is not None
    assert estimate.input_usd == Decimal("1.00000000")
    assert estimate.cached_input_usd == Decimal("0.10000000")


def test_dated_snapshot_uses_family_price() -> None:
    usage = TokenUsage(input_tokens=1_000_000, output_tokens=0)
    estimate = estimate_openai_cost("gpt-5.6-terra-2026-08-01", usage)
    assert estimate is not None
    assert estimate.total_usd == Decimal("2.00000000")
