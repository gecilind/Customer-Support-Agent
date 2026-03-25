from fastapi import APIRouter, Depends

from api.controllers.conversation_controller import ConversationController
from api.dependencies import get_conversation_controller
from schemas.conversation import ConversationResponse, MessageResponse


router = APIRouter(tags=["conversations"])


@router.post("/conversations", response_model=ConversationResponse)
async def create_conversation(
    controller: ConversationController = Depends(get_conversation_controller),
) -> ConversationResponse:
    return await controller.create_conversation()


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageResponse])
async def list_messages(
    conversation_id: str,
    controller: ConversationController = Depends(get_conversation_controller),
) -> list[MessageResponse]:
    return await controller.get_messages(conversation_id)
