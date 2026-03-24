from collections.abc import AsyncGenerator

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession

from api.controllers.health_controller import HealthController
from api.controllers.ingest_controller import IngestController
from repositories.health_repository import HealthRepository
from repositories.manual_repository import ManualRepository
from services.health_service import HealthService
from services.ingestion_service import IngestionService


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


def get_ingestion_service(manual_repository: ManualRepository = Depends(get_manual_repository)) -> IngestionService:
    return IngestionService(manual_repository)


def get_ingest_controller(ingestion_service: IngestionService = Depends(get_ingestion_service)) -> IngestController:
    return IngestController(ingestion_service)
