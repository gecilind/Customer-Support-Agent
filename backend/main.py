import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

logging.basicConfig(level=logging.INFO)

from api.routers import chat_router, conversation_router, health_router, ingest_router
from db.supabase_pool import get_engine, get_session_factory
from middleware.cors import register_cors
from middleware.request_handler import request_handler_middleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.db_engine = get_engine()
    app.state.db_session_factory = get_session_factory()
    yield
    await app.state.db_engine.dispose()


app = FastAPI(title="Infleet AI Support Agent", lifespan=lifespan)
register_cors(app)
app.middleware("http")(request_handler_middleware)
app.include_router(health_router.router)
app.include_router(ingest_router.router)
app.include_router(chat_router.router)
app.include_router(conversation_router.router)
