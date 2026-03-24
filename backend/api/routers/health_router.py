from fastapi import APIRouter, Depends

from api.controllers.health_controller import HealthController
from api.dependencies import get_health_controller


router = APIRouter(tags=["health"])


@router.get("/health")
async def health(controller: HealthController = Depends(get_health_controller)) -> dict[str, str]:
    return await controller.get_health()
