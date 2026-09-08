from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.llm.types import TokenUsage


@dataclass(frozen=True, slots=True)
class ModelPrice:
    input_per_million: Decimal
    cached_input_per_million: Decimal
    output_per_million: Decimal
    cache_write_multiplier: Decimal = Decimal("1.25")


# OpenAI standard text pricing snapshot used by this lab on 2026-09-01.
# This is an ESTIMATE only: long-context, service tier, Batch/Flex/Fast, tools,
# regional processing, promotions or future pricing changes can alter billing.
OPENAI_STANDARD_PRICING: dict[str, ModelPrice] = {
    "gpt-5.6": ModelPrice(Decimal("4.00"), Decimal("0.40"), Decimal("20.00")),
    "gpt-5.6-sol": ModelPrice(Decimal("4.00"), Decimal("0.40"), Decimal("20.00")),
    "gpt-5.6-terra": ModelPrice(Decimal("2.00"), Decimal("0.20"), Decimal("12.00")),
    "gpt-5.6-luna": ModelPrice(Decimal("0.20"), Decimal("0.02"), Decimal("1.20")),
}


@dataclass(frozen=True, slots=True)
class CostEstimate:
    input_usd: Decimal
    cached_input_usd: Decimal
    cache_write_usd: Decimal
    output_usd: Decimal
    total_usd: Decimal


ZERO = Decimal("0")
MILLION = Decimal("1000000")


def _resolve_price(model: str) -> ModelPrice | None:
    if model in OPENAI_STANDARD_PRICING:
        return OPENAI_STANDARD_PRICING[model]
    # Provider responses can resolve an alias to a dated/suffixed snapshot.
    for prefix in ("gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna"):
        if model.startswith(prefix + "-"):
            return OPENAI_STANDARD_PRICING[prefix]
    return None


def estimate_openai_cost(model: str, usage: TokenUsage) -> CostEstimate | None:
    price = _resolve_price(model)
    if price is None:
        return None

    cached = max(0, usage.cached_input_tokens)
    cache_write = max(0, usage.cache_write_tokens)
    # usage.input_tokens includes all input tokens. Avoid double-counting cached/write tokens.
    uncached = max(0, usage.input_tokens - cached - cache_write)

    input_cost = Decimal(uncached) / MILLION * price.input_per_million
    cached_cost = Decimal(cached) / MILLION * price.cached_input_per_million
    cache_write_cost = (
        Decimal(cache_write)
        / MILLION
        * price.input_per_million
        * price.cache_write_multiplier
    )
    output_cost = Decimal(max(0, usage.output_tokens)) / MILLION * price.output_per_million
    total = input_cost + cached_cost + cache_write_cost + output_cost

    quant = Decimal("0.00000001")
    return CostEstimate(
        input_usd=input_cost.quantize(quant),
        cached_input_usd=cached_cost.quantize(quant),
        cache_write_usd=cache_write_cost.quantize(quant),
        output_usd=output_cost.quantize(quant),
        total_usd=total.quantize(quant),
    )
