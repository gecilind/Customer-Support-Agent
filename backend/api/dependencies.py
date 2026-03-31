from collections.abc import AsyncGenerator

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession

from openai import AsyncOpenAI

from api.controllers.chat_controller import ChatController
from api.controllers.conversation_controller import ConversationController
from api.controllers.health_controller import HealthController
from api.controllers.ingest_controller import IngestController
from api.controllers.manual_controller import ManualController
from api.controllers.ticket_controller import TicketController
from config import Settings, get_settings
from repositories.conversation_repository import ConversationRepository
from repositories.health_repository import HealthRepository
from repositories.kb_repository import KBRepository
from repositories.manual_repository import ManualRepository
from repositories.ticket_repository import TicketRepository
from services.chat_service import ChatService
from services.embedding_service import EmbeddingService
from services.health_service import HealthService
from services.ingestion_service import IngestionService
from services.kb_service import KBService
from services.manual_service import ManualService
from services.ticket_service import TicketService


def get_app_settings() -> Settings:
    return get_settings()


def get_supabase_session_factory(request: Request) -> async_sessionmaker[AsyncSession]:
    return request.app.state.db_session_factory


async def get_supabase_session(
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_supabase_session_factory),
) -> AsyncGenerator[AsyncSession, None]:
    async with session_factory() as session:
        yield session


def get_health_repository(session: AsyncSession = Depends(get_supabase_session)) -> HealthRepository:
    return HealthRepository(session)


def get_health_service(health_repository: HealthRepository = Depends(get_health_repository)) -> HealthService:
    return HealthService(health_repository)


def get_health_controller(health_service: HealthService = Depends(get_health_service)) -> HealthController:
    return HealthController(health_service)


def get_manual_repository(session: AsyncSession = Depends(get_supabase_session)) -> ManualRepository:
    return ManualRepository(session)


def get_embedding_service(settings: Settings = Depends(get_app_settings)) -> EmbeddingService:
    return EmbeddingService(openai_api_key=settings.openai_api_key)


def get_ingestion_service(
    manual_repository: ManualRepository = Depends(get_manual_repository),
    embedding_service: EmbeddingService = Depends(get_embedding_service),
) -> IngestionService:
    return IngestionService(manual_repository, embedding_service)


def get_ingest_controller(ingestion_service: IngestionService = Depends(get_ingestion_service)) -> IngestController:
    return IngestController(ingestion_service)


def get_manual_service(manual_repository: ManualRepository = Depends(get_manual_repository)) -> ManualService:
    return ManualService(manual_repository)


def get_manual_controller(manual_service: ManualService = Depends(get_manual_service)) -> ManualController:
    return ManualController(manual_service)


def get_conversation_repository(session: AsyncSession = Depends(get_supabase_session)) -> ConversationRepository:
    return ConversationRepository(session)


def get_openai_client(settings: Settings = Depends(get_app_settings)) -> AsyncOpenAI:
    return AsyncOpenAI(api_key=settings.openai_api_key)


def get_kb_repository(session: AsyncSession = Depends(get_supabase_session)) -> KBRepository:
    return KBRepository(session)


def get_kb_service(
    embedding_service: EmbeddingService = Depends(get_embedding_service),
    kb_repository: KBRepository = Depends(get_kb_repository),
) -> KBService:
    return KBService(embedding_service, kb_repository)


def get_chat_service(
    conversation_repository: ConversationRepository = Depends(get_conversation_repository),
    kb_service: KBService = Depends(get_kb_service),
    openai_client: AsyncOpenAI = Depends(get_openai_client),
    settings: Settings = Depends(get_app_settings),
) -> ChatService:
    return ChatService(
        conversation_repository,
        kb_service,
        openai_client,
        settings.openai_chat_model,
    )


def get_chat_controller(chat_service: ChatService = Depends(get_chat_service)) -> ChatController:
    return ChatController(chat_service)


def get_conversation_controller(
    conversation_repository: ConversationRepository = Depends(get_conversation_repository),
) -> ConversationController:
    return ConversationController(conversation_repository)


def get_ticket_repository(
    request: Request,
    session: AsyncSession = Depends(get_supabase_session),
    settings: Settings = Depends(get_app_settings),
) -> TicketRepository:
    return TicketRepository(
        http_client=request.app.state.http_client,
        session=session,
        settings=settings,
    )


def get_ticket_service(
    ticket_repository: TicketRepository = Depends(get_ticket_repository),
) -> TicketService:
    return TicketService(ticket_repository)


def get_ticket_controller(
    ticket_service: TicketService = Depends(get_ticket_service),
) -> TicketController:
    return TicketController(ticket_service)
