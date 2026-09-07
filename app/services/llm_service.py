from __future__ import annotations

import hashlib
import json
import time
from typing import Any

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.llm.base import LLMProvider
from app.llm.exceptions import LLMProviderError
from app.llm.pricing import estimate_openai_cost
from app.llm.types import LLMResult, TokenUsage
from app.models.agent_run import AgentRun
from app.models.user import User
from app.services.tool_service import ToolService
from app.tools.exceptions import ToolExecutionError


DEFAULT_INSTRUCTIONS = (
    "Você é um assistente comercial profissional. Responda em português do Brasil, "
    "de forma objetiva, útil e sem inventar fatos."
)

LEAD_CLASSIFIER_INSTRUCTIONS = (
    "Classifique a mensagem comercial somente com base no texto recebido. "
    "Se o usuário pedir explicitamente uma pessoa/atendente, needs_human deve ser true "
    "e intent deve ser human_request, mesmo que também exista intenção de compra/agendamento. "
    "Não invente dados ausentes."
)

TOOL_AGENT_INSTRUCTIONS = (
    "Você é um agente comercial. Use ferramentas quando precisar consultar dados ou executar ações. "
    "Nunca invente preço, cliente, disponibilidade, políticas, conteúdo documental ou confirmação de criação. "
    "Para políticas, implantação, documentação ou conhecimento do cliente, use search_knowledge. "
    "Somente afirme que uma ação ocorreu depois de receber o resultado da ferramenta. "
    "Responda em português do Brasil e seja objetivo."
)


class LLMService:
    def __init__(self, provider: LLMProvider) -> None:
        self.provider = provider

    @staticmethod
    def _hash_prompt(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    @staticmethod
    def _model(provider_name: str) -> str:
        return settings.openai_model if provider_name == "openai" else settings.mock_model

    async def _start_run(self, *, db: AsyncSession, current_user: User, operation: str, input_text: str) -> AgentRun:
        run = AgentRun(
            tenant_id=current_user.tenant_id,
            user_id=current_user.id,
            operation=operation,
            provider=self.provider.name,
            model=self._model(self.provider.name),
            status="running",
            prompt_hash=self._hash_prompt(input_text),
            input_chars=len(input_text),
        )
        db.add(run)
        await db.commit()
        await db.refresh(run)
        return run

    async def _complete_run(
        self,
        *,
        db: AsyncSession,
        run: AgentRun,
        result: LLMResult,
        latency_ms: int,
        schema_name: str | None = None,
    ) -> None:
        usage = result.usage
        run.status = "completed"
        run.provider = result.provider
        run.model = result.model
        run.provider_request_id = result.request_id
        run.output_chars = len(result.text)
        run.output_hash = self._hash_prompt(result.text)
        run.schema_name = schema_name
        run.input_tokens = usage.input_tokens
        run.cached_input_tokens = usage.cached_input_tokens
        run.cache_write_tokens = usage.cache_write_tokens
        run.output_tokens = usage.output_tokens
        run.reasoning_tokens = usage.reasoning_tokens
        run.total_tokens = usage.total_tokens
        run.provider_response_count = result.provider_response_count
        run.tool_call_count = result.tool_call_count
        run.latency_ms = latency_ms
        if result.provider == "openai":
            estimate = estimate_openai_cost(result.model, usage)
            run.estimated_cost_usd = estimate.total_usd if estimate is not None else None
        else:
            run.estimated_cost_usd = None
        await db.commit()
        await db.refresh(run)

    async def _fail_run(self, *, db: AsyncSession, run: AgentRun, exc: Exception, latency_ms: int, code: str) -> None:
        run.status = "failed"
        run.latency_ms = latency_ms
        run.error_code = code
        run.error_message = str(exc)[:2000]
        await db.commit()

    async def generate(self, *, db: AsyncSession, current_user: User, input_text: str, instructions: str | None = None, operation: str = "generate") -> tuple[AgentRun, LLMResult]:
        run = await self._start_run(db=db, current_user=current_user, operation=operation, input_text=input_text)
        started = time.perf_counter()
        try:
            result = await self.provider.generate(
                input_text=input_text,
                instructions=instructions or DEFAULT_INSTRUCTIONS,
                model=self._model(self.provider.name),
            )
        except LLMProviderError as exc:
            latency_ms = max(0, round((time.perf_counter() - started) * 1000))
            await self._fail_run(db=db, run=run, exc=exc, latency_ms=latency_ms, code=exc.code)
            raise
        latency_ms = max(0, round((time.perf_counter() - started) * 1000))
        await self._complete_run(db=db, run=run, result=result, latency_ms=latency_ms)
        return run, result

    async def generate_structured(
        self,
        *,
        db: AsyncSession,
        current_user: User,
        input_text: str,
        output_model: type[BaseModel],
        schema_name: str,
        instructions: str,
        operation: str,
    ) -> tuple[AgentRun, LLMResult, BaseModel]:
        run = await self._start_run(db=db, current_user=current_user, operation=operation, input_text=input_text)
        started = time.perf_counter()
        try:
            result = await self.provider.generate_structured(
                input_text=input_text,
                instructions=instructions,
                model=self._model(self.provider.name),
                schema_name=schema_name,
                json_schema=output_model.model_json_schema(),
            )
            parsed = output_model.model_validate(result.structured_data)
            result.structured_data = parsed.model_dump(mode="json")
        except LLMProviderError as exc:
            latency_ms = max(0, round((time.perf_counter() - started) * 1000))
            await self._fail_run(db=db, run=run, exc=exc, latency_ms=latency_ms, code=exc.code)
            raise
        except Exception as exc:
            wrapped = LLMProviderError(
                f"Structured output validation failed: {exc}",
                code="schema_validation_error",
                retryable=False,
            )
            latency_ms = max(0, round((time.perf_counter() - started) * 1000))
            await self._fail_run(db=db, run=run, exc=wrapped, latency_ms=latency_ms, code=wrapped.code)
            raise wrapped from exc

        latency_ms = max(0, round((time.perf_counter() - started) * 1000))
        await self._complete_run(db=db, run=run, result=result, latency_ms=latency_ms, schema_name=schema_name)
        return run, result, parsed

    async def run_tool_agent(
        self,
        *,
        db: AsyncSession,
        current_user: User,
        input_text: str,
        tool_service: ToolService,
        client_idempotency_key: str,
        max_turns: int = 4,
        instructions: str | None = None,
    ) -> tuple[AgentRun, LLMResult, list[Any]]:
        run = await self._start_run(db=db, current_user=current_user, operation="tool_agent", input_text=input_text)
        started = time.perf_counter()
        aggregate = TokenUsage()
        executed_audits: list[Any] = []
        provider_responses = 0
        last_request_id: str | None = None
        input_data: str | list[Any] = input_text
        model = self._model(self.provider.name)

        try:
            for _ in range(max_turns):
                turn = await self.provider.generate_with_tools(
                    input_data=input_data,
                    instructions=instructions or TOOL_AGENT_INSTRUCTIONS,
                    model=model,
                    tools=tool_service.registry.definitions(),
                )
                provider_responses += 1
                last_request_id = turn.request_id or last_request_id
                aggregate.add(turn.usage)

                if not turn.tool_calls:
                    if not turn.text:
                        raise LLMProviderError("Tool loop ended without final text", code="empty_tool_agent_output")
                    result = LLMResult(
                        provider=turn.provider,
                        model=turn.model,
                        text=turn.text,
                        request_id=last_request_id,
                        usage=aggregate,
                        provider_response_count=provider_responses,
                        tool_call_count=len(executed_audits),
                    )
                    latency_ms = max(0, round((time.perf_counter() - started) * 1000))
                    await self._complete_run(db=db, run=run, result=result, latency_ms=latency_ms)
                    return run, result, executed_audits

                next_input = list(turn.continuation_items)
                for call in turn.tool_calls:
                    audit, tool_result = await tool_service.execute(
                        db=db,
                        current_user=current_user,
                        agent_run_id=run.id,
                        provider_call_id=call.call_id,
                        tool_name=call.name,
                        arguments=call.arguments,
                        client_idempotency_key=client_idempotency_key,
                    )
                    executed_audits.append(audit)
                    next_input.append(
                        {
                            "type": "function_call_output",
                            "call_id": call.call_id,
                            "output": json.dumps(tool_result, ensure_ascii=False, default=str),
                        }
                    )
                input_data = next_input

            raise LLMProviderError(
                f"Tool loop exceeded {max_turns} provider turns",
                code="tool_loop_limit",
                retryable=False,
            )
        except ToolExecutionError as exc:
            latency_ms = max(0, round((time.perf_counter() - started) * 1000))
            await self._fail_run(db=db, run=run, exc=exc, latency_ms=latency_ms, code=exc.code)
            raise
        except LLMProviderError as exc:
            latency_ms = max(0, round((time.perf_counter() - started) * 1000))
            await self._fail_run(db=db, run=run, exc=exc, latency_ms=latency_ms, code=exc.code)
            raise
