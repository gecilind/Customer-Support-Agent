from fastapi import APIRouter, Depends, WebSocket

from api.controllers.voice_controller import VoiceController
from api.dependencies import get_voice_controller

router = APIRouter()


@router.websocket("/voice-relay")
async def voice_relay(
    websocket: WebSocket,
    controller: VoiceController = Depends(get_voice_controller),
) -> None:
    await controller.handle_connection(websocket)
