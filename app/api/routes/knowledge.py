from __future__ import annotations
from typing import Annotated
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import CurrentUser, require_roles
from app.core.config import settings
from app.db.session import get_db
from app.llm.factory import create_llm_provider
from app.models.user import User, UserRole
from app.schemas.knowledge import KnowledgeConfigRead, KnowledgeDocumentRead, KnowledgeIngestResponse, KnowledgeQueryResponse, KnowledgeSearchRequest, KnowledgeSearchResponse
from app.services.knowledge_service import KnowledgeService
from app.services.llm_service import LLMService
from app.services.tenant_config_service import TenantConfigService

router=APIRouter(prefix="/knowledge", tags=["knowledge-rag"])
KnowledgeAdmin=Annotated[User, Depends(require_roles(UserRole.ADMIN, UserRole.MANAGER))]

@router.get("/config", response_model=KnowledgeConfigRead)
async def config(current_user: CurrentUser, db: Annotated[AsyncSession, Depends(get_db)]):
    tenant_config = await TenantConfigService().get(db=db, tenant_id=current_user.tenant_id)
    return KnowledgeConfigRead(vector_backend="postgresql+pgvector", index_type="hnsw/cosine", embedding_provider=settings.embedding_provider, embedding_model=settings.openai_embedding_model if settings.embedding_provider=="openai" else "mock-embedding-v0.6", embedding_dimensions=settings.embedding_dimensions, chunk_chars=settings.knowledge_chunk_chars, chunk_overlap_chars=settings.knowledge_chunk_overlap_chars, supported_types=["pdf","docx","txt","md"], rag_top_k=tenant_config.rag_top_k, rag_min_similarity=float(tenant_config.rag_min_similarity))

@router.post("/documents", response_model=KnowledgeIngestResponse)
async def upload_document(current_user: KnowledgeAdmin, db: Annotated[AsyncSession, Depends(get_db)], file: UploadFile=File(...)):
    try:
        data=await file.read(); service=KnowledgeService()
        doc,dedup,tokens=await service.ingest(db=db,current_user=current_user,filename=file.filename or "upload",content_type=file.content_type or "application/octet-stream",data=data)
        return KnowledgeIngestResponse(document=KnowledgeDocumentRead.model_validate(doc),deduplicated=dedup,embedding_tokens=tokens,estimated_embedding_cost_usd=service.embedding_cost(doc.embedding_model,tokens))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

@router.get("/documents", response_model=list[KnowledgeDocumentRead])
async def list_documents(current_user: CurrentUser, db: Annotated[AsyncSession, Depends(get_db)]):
    return await KnowledgeService().list_documents(db=db,current_user=current_user)

@router.post("/search", response_model=KnowledgeSearchResponse)
async def search_knowledge(payload: KnowledgeSearchRequest, current_user: CurrentUser, db: Annotated[AsyncSession, Depends(get_db)]):
    service=KnowledgeService(); emb,sources=await service.search(db=db,current_user=current_user,query=payload.query,top_k=payload.top_k)
    return KnowledgeSearchResponse(query=payload.query,embedding_model=emb.model,embedding_tokens=emb.input_tokens,sources=sources)

@router.post("/query", response_model=KnowledgeQueryResponse)
async def query_knowledge(payload: KnowledgeSearchRequest, current_user: CurrentUser, db: Annotated[AsyncSession, Depends(get_db)]):
    service=KnowledgeService(); run,answer,sources=await service.answer(db=db,current_user=current_user,query=payload.query,llm_service=LLMService(create_llm_provider()))
    return KnowledgeQueryResponse(run_id=run.id if run else None,answer=answer,sources=sources)
