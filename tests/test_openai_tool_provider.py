import json
from types import SimpleNamespace

import pytest

from app.llm.providers.openai_provider import OpenAIProvider


class FakeResponses:
    def __init__(self):
        self.kwargs = None

    async def create(self, **kwargs):
        self.kwargs = kwargs
        call = SimpleNamespace(
            type="function_call",
            call_id="call_test",
            name="check_price",
            arguments=json.dumps({"product_code": "PRO"}),
        )
        return SimpleNamespace(
            output=[call],
            output_text="",
            model="gpt-5.6-terra",
            usage=None,
            _request_id="req_test",
        )


class FakeClient:
    def __init__(self):
        self.responses = FakeResponses()


@pytest.mark.asyncio
async def test_openai_tool_turn_uses_strict_control_parameters():
    provider = OpenAIProvider()
    fake = FakeClient()
    provider.client = fake

    tools = [{
        "type": "function",
        "name": "check_price",
        "description": "test",
        "parameters": {
            "type": "object",
            "properties": {"product_code": {"type": "string"}},
            "required": ["product_code"],
            "additionalProperties": False,
        },
        "strict": True,
    }]

    result = await provider.generate_with_tools(
        input_data="qual o preço do PRO?",
        instructions="use tools",
        model="gpt-5.6-terra",
        tools=tools,
    )

    assert result.tool_calls[0].name == "check_price"
    assert result.tool_calls[0].arguments == {"product_code": "PRO"}
    assert fake.responses.kwargs["parallel_tool_calls"] is False
    assert fake.responses.kwargs["tool_choice"] == "auto"
    assert fake.responses.kwargs["store"] is False
    assert fake.responses.kwargs["include"] == ["reasoning.encrypted_content"]
