from __future__ import annotations

from typing import Any, Literal

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from langgraph.types import interrupt

from app.agent.state import SalesAgentContext, SalesAgentState
from app.schemas.ai import LeadClassification
from app.services.llm_service import LEAD_CLASSIFIER_INSTRUCTIONS
from app.services.tenant_config_service import TenantConfigService


GRAPH_DIRECT_INSTRUCTIONS = (
    "Você é um agente comercial profissional. Responda em português do Brasil, de forma objetiva. "
    "Use o histórico fornecido somente como contexto da conversa. Não invente preços, disponibilidade, "
    "clientes ou ações executadas. Perguntas de preço e agenda são roteadas para ferramentas em outro nó."
)


def _message_role(message: Any) -> str:
    if isinstance(message, dict):
        return str(message.get("role", "unknown"))
    role = getattr(message, "type", None) or getattr(message, "role", None)
    if role == "human":
        return "user"
    if role == "ai":
        return "assistant"
    return str(role or "unknown")


def _message_content(message: Any) -> str:
    if isinstance(message, dict):
        return str(message.get("content", ""))
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    return str(content)


def _render_transcript(messages: list[Any], *, max_messages: int = 12) -> str:
    selected = messages[-max_messages:]
    lines: list[str] = []
    for message in selected:
        role = _message_role(message)
        content = _message_content(message).strip()
        if content:
            lines.append(f"{role}: {content}")
    return "\n".join(lines)


async def classify_node(
    state: SalesAgentState,
    runtime: Runtime[SalesAgentContext],
) -> dict[str, Any]:
    transcript = _render_transcript(state.get("messages", []))
    classifier_input = (
        "Classifique a ÚLTIMA mensagem considerando o histórico abaixo quando necessário.\n\n"
        f"HISTÓRICO:\n{transcript}\n"
    )
    run, _result, parsed = await runtime.context.llm_service.generate_structured(
        db=runtime.context.db,
        current_user=runtime.context.current_user,
        input_text=classifier_input,
        output_model=LeadClassification,
        schema_name="lead_classification",
        instructions=LEAD_CLASSIFIER_INSTRUCTIONS,
        operation="graph_classify",
    )
    if parsed.needs_human:
        route = "handoff_pending"
        review_status = "pending"
    elif parsed.intent in {"pricing", "scheduling", "product_interest", "support", "objection", "other"}:
        route = "tool_agent"
        review_status = "none"
    else:
        route = "respond"
        review_status = "none"

    return {
        "classification": parsed.model_dump(mode="json"),
        "human_required": parsed.needs_human,
        "route": route,
        "human_review_status": review_status,
        "human_review_note": "",
        "reviewed_by_user_id": "",
        "agent_run_ids": [str(run.id)],
    }


def route_after_classification(state: SalesAgentState) -> Literal["handoff", "tool_agent", "respond"]:
    classification = state.get("classification") or {}
    if bool(classification.get("needs_human")):
        return "handoff"
    if classification.get("intent") in {"pricing", "scheduling", "product_interest", "support", "objection", "other"}:
        return "tool_agent"
    return "respond"


async def tool_agent_node(
    state: SalesAgentState,
    runtime: Runtime[SalesAgentContext],
) -> dict[str, Any]:
    transcript = _render_transcript(state.get("messages", []))
    prompt = (
        "Considere o histórico abaixo e responda à última mensagem. "
        "Use as ferramentas disponíveis sempre que precisar de dados factuais ou executar uma ação.\n\n"
        f"HISTÓRICO:\n{transcript}"
    )
    run, result, audits = await runtime.context.llm_service.run_tool_agent(
        db=runtime.context.db,
        current_user=runtime.context.current_user,
        input_text=prompt,
        tool_service=runtime.context.tool_service,
        client_idempotency_key=runtime.context.client_idempotency_key,
        instructions=TenantConfigService.tool_instructions(runtime.context.tenant_config),
    )
    return {
        "route": "tool_agent",
        "final_output": result.text,
        "messages": [{"role": "assistant", "content": result.text}],
        "agent_run_ids": [str(run.id)],
        "tool_call_ids": [str(audit.id) for audit in audits],
    }


async def respond_node(
    state: SalesAgentState,
    runtime: Runtime[SalesAgentContext],
) -> dict[str, Any]:
    transcript = _render_transcript(state.get("messages", []))
    prompt = (
        "Responda à última mensagem do cliente usando o histórico abaixo como contexto.\n\n"
        f"HISTÓRICO:\n{transcript}"
    )
    run, result = await runtime.context.llm_service.generate(
        db=runtime.context.db,
        current_user=runtime.context.current_user,
        input_text=prompt,
        instructions=TenantConfigService.direct_instructions(runtime.context.tenant_config),
    )
    return {
        "route": "respond",
        "final_output": result.text,
        "messages": [{"role": "assistant", "content": result.text}],
        "agent_run_ids": [str(run.id)],
    }


async def handoff_node(
    state: SalesAgentState,
    runtime: Runtime[SalesAgentContext],
) -> dict[str, Any]:
    # IMPORTANT: keep everything before interrupt() side-effect free. LangGraph
    # restarts this node from the beginning when Command(resume=...) is used.
    # Any write before interrupt() would therefore need its own idempotency guard.
    del runtime
    classification = state.get("classification") or {}
    review = interrupt(
        {
            "type": "human_handoff_approval",
            "requested_action": "transfer_to_human",
            "thread_id": state.get("external_thread_id", ""),
            "latest_input": state.get("latest_input", ""),
            "reason": str(classification.get("summary", "Human handoff requested")),
            "allowed_decisions": ["approve", "reject"],
        }
    )

    decision = str((review or {}).get("decision", "")).lower() if isinstance(review, dict) else ""
    note = str((review or {}).get("note", "")) if isinstance(review, dict) else ""
    reviewer_user_id = (
        str((review or {}).get("reviewer_user_id", "")) if isinstance(review, dict) else ""
    )

    if decision == "approve":
        text = "Encaminhamento aprovado. A conversa será assumida por atendimento humano."
        return {
            "route": "handoff",
            "human_required": True,
            "human_review_status": "approved",
            "human_review_note": note,
            "reviewed_by_user_id": reviewer_user_id,
            "final_output": text,
            "messages": [{"role": "assistant", "content": text}],
        }

    if decision == "reject":
        text = "O encaminhamento para atendimento humano não foi aprovado. O atendimento por IA pode continuar."
        return {
            "route": "handoff_rejected",
            "human_required": False,
            "human_review_status": "rejected",
            "human_review_note": note,
            "reviewed_by_user_id": reviewer_user_id,
            "final_output": text,
            "messages": [{"role": "assistant", "content": text}],
        }

    # The public resume endpoint validates this, so reaching here means a
    # malformed internal resume payload rather than ordinary user input.
    raise ValueError("Unsupported human review decision")


def build_sales_agent_graph(checkpointer: Any):
    builder = StateGraph(SalesAgentState, context_schema=SalesAgentContext)
    builder.add_node("classify", classify_node)
    builder.add_node("tool_agent", tool_agent_node)
    builder.add_node("respond", respond_node)
    builder.add_node("handoff", handoff_node)

    builder.add_edge(START, "classify")
    builder.add_conditional_edges(
        "classify",
        route_after_classification,
        {
            "tool_agent": "tool_agent",
            "respond": "respond",
            "handoff": "handoff",
        },
    )
    builder.add_edge("tool_agent", END)
    builder.add_edge("respond", END)
    builder.add_edge("handoff", END)
    return builder.compile(checkpointer=checkpointer)
