from fastapi import APIRouter

from app.api.routes import agent, ai, auth, channels, conversations, customers, health, knowledge, leads, tenant_config, users, voice

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(customers.router)
api_router.include_router(users.router)
api_router.include_router(conversations.router)
api_router.include_router(leads.router)
api_router.include_router(ai.router)
api_router.include_router(agent.router)
api_router.include_router(knowledge.router)
api_router.include_router(tenant_config.router)
api_router.include_router(channels.router)

api_router.include_router(voice.router)
