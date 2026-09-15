from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_check_price_keeps_catalog_as_primary_source_and_recommends_rag_fallback():
    source = _read("app/tools/builtin.py")
    check_price_block = source.split("async def check_price", 1)[1].split(
        "async def get_customer_by_email", 1
    )[0]

    assert "TenantProduct.tenant_id == ctx.current_user.tenant_id" in check_price_block
    assert '"source": "catalog"' in check_price_block
    assert '"authoritative_price": True' in check_price_block
    assert '"fallback_recommended": True' in check_price_block
    assert '"fallback_tool": "search_knowledge"' in check_price_block
    assert '"fallback_query"' in check_price_block

    # Guard rail: check_price não deve executar o RAG por conta própria.
    # O fallback permanece visível/auditável como uma segunda tool call do agente.
    assert "KnowledgeService().search(" not in check_price_block


def test_registry_documents_price_precedence_and_fallback():
    source = _read("app/tools/registry.py")

    assert "Use sempre primeiro para preço" in source
    assert "fallback_recommended=true" in source
    assert "chame search_knowledge com fallback_query" in source
    assert "não substitui um preço oficial encontrado no catálogo" in source


def test_global_tool_agent_instructions_require_price_fallback():
    source = _read("app/services/llm_service.py")

    assert "Para perguntas de preço, use check_price primeiro" in source
    assert "fallback_recommended=true" in source
    assert "você DEVE chamar search_knowledge" in source
    assert "o catálogo é a fonte oficial" in source
    assert "informação documental" in source


def test_tenant_tool_instructions_require_price_fallback():
    source = _read("app/services/tenant_config_service.py")

    assert "Para perguntas de preço, use check_price primeiro" in source
    assert "fallback_recommended=true" in source
    assert "chame search_knowledge com fallback_query" in source
    assert "catálogo estruturado é a fonte oficial" in source
    assert "informação documental" in source
