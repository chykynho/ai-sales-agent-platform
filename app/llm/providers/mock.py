from __future__ import annotations

import json
import re
from typing import Any

from app.llm.types import LLMResult, TokenUsage, ToolCallRequest, ToolTurnResult


class MockLLMProvider:
    name = "mock"

    @staticmethod
    def _usage(input_text: str, output_text: str) -> TokenUsage:
        input_tokens = max(1, len(input_text) // 4)
        output_tokens = max(1, len(output_text) // 4)
        return TokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
        )

    async def generate(self, *, input_text: str, instructions: str, model: str) -> LLMResult:
        del instructions
        text = f"[mock] Resposta recebida para: {input_text[:120]}"
        return LLMResult(
            provider=self.name,
            model=model,
            text=text,
            request_id="mock-request",
            usage=self._usage(input_text, text),
        )

    async def generate_structured(
        self,
        *,
        input_text: str,
        instructions: str,
        model: str,
        schema_name: str,
        json_schema: dict[str, Any],
    ) -> LLMResult:
        del instructions, schema_name, json_schema
        lowered = input_text.lower()
        human = any(term in lowered for term in ("humano", "atendente", "pessoa"))
        hot = any(term in lowered for term in ("comprar", "contratar", "fechar", "agendar"))
        data = {
            "intent": "human_request" if human else ("scheduling" if "agendar" in lowered else "product_interest"),
            "lead_temperature": "hot" if hot else "warm",
            "needs_human": human,
            "confidence": 0.99,
            "summary": "Classificação determinística do provider mock para validação local.",
        }
        text = json.dumps(data, ensure_ascii=False)
        return LLMResult(
            provider=self.name,
            model=model,
            text=text,
            request_id="mock-request-structured",
            structured_data=data,
            usage=self._usage(input_text, text),
        )

    async def generate_with_tools(
        self,
        *,
        input_data: str | list[Any],
        instructions: str,
        model: str,
        tools: list[dict[str, Any]],
    ) -> ToolTurnResult:
        del instructions, tools
        if isinstance(input_data, list):
            outputs = [x for x in input_data if isinstance(x, dict) and x.get("type") == "function_call_output"]
            result_text = outputs[-1]["output"] if outputs else "{}"
            text = f"[mock] Ferramenta executada com sucesso. Resultado: {result_text}"
            return ToolTurnResult(
                provider=self.name,
                model=model,
                text=text,
                request_id="mock-tool-final",
                usage=self._usage(result_text, text),
                tool_calls=[],
                continuation_items=[],
            )

        lowered = input_data.lower()
        call: ToolCallRequest | None = None
        if "preço" in lowered or "preco" in lowered or "check_price" in lowered:
            code = "PRO" if "pro" in lowered else "STARTER"
            call = ToolCallRequest("mock-call-price", "check_price", {"product_code": code})
        elif "create_lead" in lowered or "cadastre" in lowered or "cadastrar" in lowered:
            email_match = re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", input_data)
            email = email_match.group(0) if email_match else "lead@example.com"
            call = ToolCallRequest(
                "mock-call-lead",
                "create_lead",
                {"name": "Maria Silva", "email": email, "interest": "Plano PRO"},
            )
        elif "cliente" in lowered and "email" in lowered:
            email_match = re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", input_data)
            call = ToolCallRequest(
                "mock-call-customer",
                "get_customer_by_email",
                {"email": email_match.group(0) if email_match else "cliente@example.com"},
            )
        elif "horário" in lowered or "horario" in lowered or "disponibilidade" in lowered:
            call = ToolCallRequest(
                "mock-call-availability",
                "check_availability",
                {"date": "2026-09-03", "time": "14:00"},
            )

        if call is None:
            text = "[mock] Nenhuma ferramenta necessária para esta mensagem."
            return ToolTurnResult(
                provider=self.name,
                model=model,
                text=text,
                request_id="mock-tool-no-call",
                usage=self._usage(input_data, text),
                tool_calls=[],
                continuation_items=[],
            )

        continuation = [{"type": "function_call", "call_id": call.call_id, "name": call.name, "arguments": json.dumps(call.arguments)}]
        return ToolTurnResult(
            provider=self.name,
            model=model,
            text="",
            request_id="mock-tool-call",
            usage=self._usage(input_data, json.dumps(call.arguments)),
            tool_calls=[call],
            continuation_items=continuation,
        )
