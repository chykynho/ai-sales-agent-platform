from app.tools.builtin import CheckPriceArgs, CreateLeadArgs
from app.tools.registry import get_tool_registry


EXPECTED_TOOL_NAMES = {
    "check_price",
    "get_customer_by_email",
    "check_availability",
    "search_knowledge",
    "create_lead",
}


def test_all_tools_are_strict_json_schema_compatible():
    defs = get_tool_registry().definitions()

    # Valida o inventário esperado, em vez de depender apenas de uma contagem
    # fixa. Assim o teste informa claramente se uma tool conhecida sumiu ou se
    # uma tool inesperada foi adicionada sem atualização do contrato de testes.
    names = {tool["name"] for tool in defs}
    assert names == EXPECTED_TOOL_NAMES
    assert len(defs) == len(EXPECTED_TOOL_NAMES)

    for tool in defs:
        assert tool["type"] == "function"
        assert tool["strict"] is True
        schema = tool["parameters"]
        assert schema["additionalProperties"] is False
        assert set(schema["required"]) == set(schema["properties"].keys())


def test_args_forbid_extra_fields():
    assert CheckPriceArgs(product_code="PRO").product_code == "PRO"
    assert CreateLeadArgs(name="Maria", email="maria@example.com", interest="PRO").email == "maria@example.com"
