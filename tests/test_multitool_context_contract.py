from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import Any

from app.llm.types import TokenUsage, ToolCallRequest, ToolTurnResult
from app.services.llm_service import LLMService


class _FakeProvider:
    name = "fake"

    def __init__(self) -> None:
        self.inputs: list[str | list[Any]] = []
        self.turn = 0

    async def generate_with_tools(self, *, input_data, instructions, model, tools):
        self.inputs.append(input_data)
        self.turn += 1

        if self.turn == 1:
            return ToolTurnResult(
                provider=self.name,
                model=model,
                text="",
                request_id="req-1",
                usage=TokenUsage(input_tokens=10, output_tokens=2, total_tokens=12),
                tool_calls=[
                    ToolCallRequest(
                        call_id="call-price",
                        name="check_price",
                        arguments={"product_code": "ATLAS-GCP"},
                    )
                ],
                continuation_items=[
                    {
                        "type": "function_call",
                        "call_id": "call-price",
                        "name": "check_price",
                        "arguments": '{"product_code":"ATLAS-GCP"}',
                    }
                ],
            )

        if self.turn == 2:
            return ToolTurnResult(
                provider=self.name,
                model=model,
                text="",
                request_id="req-2",
                usage=TokenUsage(input_tokens=20, output_tokens=2, total_tokens=22),
                tool_calls=[
                    ToolCallRequest(
                        call_id="call-rag",
                        name="search_knowledge",
                        arguments={"query": "Qual é o preço do produto ATLAS-GCP?"},
                    )
                ],
                continuation_items=[
                    {
                        "type": "function_call",
                        "call_id": "call-rag",
                        "name": "search_knowledge",
                        "arguments": '{"query":"Qual é o preço do produto ATLAS-GCP?"}',
                    }
                ],
            )

        return ToolTurnResult(
            provider=self.name,
            model=model,
            text="O Atlas-GCP custa R$ 842,00 segundo a documentação disponível.",
            request_id="req-3",
            usage=TokenUsage(input_tokens=30, output_tokens=8, total_tokens=38),
            tool_calls=[],
            continuation_items=[],
        )


class _FakeRegistry:
    @staticmethod
    def definitions():
        return []


class _FakeToolService:
    registry = _FakeRegistry()

    async def execute(self, *, tool_name: str, **kwargs):
        if tool_name == "check_price":
            return (
                SimpleNamespace(id="audit-price"),
                {
                    "found": False,
                    "product_code": "ATLAS-GCP",
                    "source": "catalog",
                    "fallback_recommended": True,
                    "fallback_tool": "search_knowledge",
                    "fallback_query": "Qual é o preço do produto ATLAS-GCP?",
                },
            )
        if tool_name == "search_knowledge":
            return (
                SimpleNamespace(id="audit-rag"),
                {
                    "query": "Qual é o preço do produto ATLAS-GCP?",
                    "sources": [
                        {
                            "similarity": 0.654132,
                            "content": "O produto fictício Atlas-GCP custa R$ 842,00.",
                        }
                    ],
                },
            )
        raise AssertionError(f"unexpected tool: {tool_name}")


class _TestLLMService(LLMService):
    async def _start_run(self, **kwargs):
        return SimpleNamespace(id="run-multitool")

    async def _complete_run(self, **kwargs) -> None:
        return None

    async def _fail_run(self, **kwargs) -> None:
        return None


def test_stateless_multi_tool_loop_preserves_original_question_and_prior_tool_results():
    async def scenario():
        provider = _FakeProvider()
        service = _TestLLMService(provider)
        user = SimpleNamespace(id="user-1", tenant_id="tenant-1")

        _, result, audits = await service.run_tool_agent(
            db=SimpleNamespace(),
            current_user=user,
            input_text="E quanto ele custa? Produto em contexto: Atlas-GCP.",
            tool_service=_FakeToolService(),
            client_idempotency_key="test-multitool",
        )

        assert result.text.startswith("O Atlas-GCP custa R$ 842,00")
        assert result.provider_response_count == 3
        assert result.tool_call_count == 2
        assert len(audits) == 2
        assert len(provider.inputs) == 3

        # After the first tool hop, the original user question must still be present.
        second_input = provider.inputs[1]
        assert isinstance(second_input, list)
        second_serialized = json.dumps(second_input, ensure_ascii=False, default=str)
        assert "E quanto ele custa?" in second_serialized
        assert "fallback_recommended" in second_serialized

        # After the second tool hop, the entire transcript must still be present:
        # original question + catalog miss/fallback + RAG result with the documentary price.
        third_input = provider.inputs[2]
        assert isinstance(third_input, list)
        third_serialized = json.dumps(third_input, ensure_ascii=False, default=str)
        assert "E quanto ele custa?" in third_serialized
        assert "fallback_recommended" in third_serialized
        assert "search_knowledge" in third_serialized
        assert "R$ 842,00" in third_serialized

    asyncio.run(scenario())
