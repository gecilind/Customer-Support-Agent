from fastapi import HTTPException

from services.health_service import HealthService


class HealthController:
    def __init__(self, health_service: HealthService) -> None:
        self.health_service = health_service

    async def get_health(self) -> dict[str, str]:
        try:
            return await self.health_service.check()
        except Exception:
            raise HTTPException(status_code=503, detail={"status": "error", "db": "disconnected"})
