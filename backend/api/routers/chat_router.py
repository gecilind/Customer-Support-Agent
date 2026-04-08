from fastapi import APIRouter, Depends
from starlette.responses import StreamingResponse

from api.controllers.chat_controller import ChatController
from api.dependencies import get_chat_controller
from schemas.chat import ChatRequest


router = APIRouter(tags=["chat"])


@router.post("/chat")
async def chat(
    body: ChatRequest,
    controller: ChatController = Depends(get_chat_controller),
) -> StreamingResponse:
    return await controller.send_message(body)
