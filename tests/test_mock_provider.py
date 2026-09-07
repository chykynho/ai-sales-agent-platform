import pytest

from app.llm.providers.mock import MockLLMProvider


@pytest.mark.asyncio
async def test_mock_structured_provider() -> None:
    provider = MockLLMProvider()
    result = await provider.generate_structured(
        input_text="Quero falar com um atendente humano",
        instructions="classifique",
        model="mock-v0.2",
        schema_name="lead_classification",
        json_schema={},
    )
    assert result.structured_data is not None
    assert result.structured_data["needs_human"] is True
    assert result.structured_data["intent"] == "human_request"
