from repositories.health_repository import HealthRepository


class HealthService:
    def __init__(self, health_repository: HealthRepository) -> None:
        self.health_repository = health_repository

    async def check(self) -> dict[str, str]:
        is_connected = await self.health_repository.ping()
        if is_connected:
            return {"status": "ok", "db": "connected"}
        return {"status": "error", "db": "disconnected"}
