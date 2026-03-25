from fastapi import APIRouter, Depends

from api.controllers.chat_controller import ChatController
from api.dependencies import get_chat_controller
from schemas.chat import ChatRequest, ChatResponse


router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    controller: ChatController = Depends(get_chat_controller),
) -> ChatResponse:
    return await controller.send_message(body)
