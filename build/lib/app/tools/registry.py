from __future__ import annotations

from functools import lru_cache

from app.tools.builtin import (
    CheckAvailabilityArgs,
    CheckPriceArgs,
    CreateLeadArgs,
    GetCustomerByEmailArgs,
    SearchKnowledgeArgs,
    check_availability,
    check_price,
    create_lead,
    get_customer_by_email,
    search_knowledge,
)
from app.tools.types import ToolSpec


class ToolRegistry:
    def __init__(self, specs: list[ToolSpec]) -> None:
        self._ordered = list(specs)
        self._specs = {spec.name: spec for spec in specs}

    def get(self, name: str) -> ToolSpec | None:
        return self._specs.get(name)

    def names(self) -> list[str]:
        return [spec.name for spec in self._ordered]

    def filtered(self, allowed_names: list[str]) -> "ToolRegistry":
        allowed = set(allowed_names)
        return ToolRegistry([spec for spec in self._ordered if spec.name in allowed])

    def definitions(self) -> list[dict]:
        return [spec.definition() for spec in self._ordered]

    def public_catalog(self) -> list[dict]:
        return [
            {"name": spec.name, "description": spec.description, "write_action": spec.write_action}
            for spec in self._ordered
        ]


@lru_cache(maxsize=1)
def get_tool_registry() -> ToolRegistry:
    return ToolRegistry(
        [
            ToolSpec(name="check_price", description="Consulta o preço atual de um produto pelo código no catálogo do tenant. Use antes de informar preço.", args_model=CheckPriceArgs, handler=check_price, write_action=False),
            ToolSpec(name="get_customer_by_email", description="Busca um cliente do tenant atual pelo email. Nunca acessa outro tenant.", args_model=GetCustomerByEmailArgs, handler=get_customer_by_email, write_action=False),
            ToolSpec(name="check_availability", description="Consulta disponibilidade usando timezone e horário comercial configurados para o tenant.", args_model=CheckAvailabilityArgs, handler=check_availability, write_action=False),
            ToolSpec(name="search_knowledge", description="Busca informações factuais, políticas, implantação e documentação na base RAG do tenant atual. Use em vez de inventar informações não disponíveis em outras tools.", args_model=SearchKnowledgeArgs, handler=search_knowledge, write_action=False),
            ToolSpec(name="create_lead", description="Cria um lead comercial após o usuário fornecer nome, email e interesse.", args_model=CreateLeadArgs, handler=create_lead, write_action=True),
        ]
    )
