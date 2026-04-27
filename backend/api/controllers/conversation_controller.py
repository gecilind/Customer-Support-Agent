from fastapi import HTTPException

from schemas.conversation import (
    ConversationDetailResponse,
    ConversationListItem,
    ConversationResponse,
    MessageResponse,
)
from services.conversation_service import ConversationService


class ConversationController:
    def __init__(self, conversation_service: ConversationService) -> None:
        self._conversation_service = conversation_service

    async def list_conversations(self) -> list[ConversationListItem]:
        return await self._conversation_service.list_conversations()

    async def get_conversation_detail(self, conversation_id: str) -> ConversationDetailResponse:
        try:
            cid = int(conversation_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail={"error": "Invalid conversation_id"}) from exc

        detail = await self._conversation_service.get_conversation_detail(cid)
        if detail is None:
            raise HTTPException(status_code=404, detail={"error": "Conversation not found"})
        return detail

    async def create_conversation(self) -> ConversationResponse:
        return await self._conversation_service.create_conversation()

    async def get_messages(self, conversation_id: str) -> list[MessageResponse]:
        try:
            cid = int(conversation_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail={"error": "Invalid conversation_id"}) from exc

        messages = await self._conversation_service.get_messages(cid)
        if messages is None:
            raise HTTPException(status_code=404, detail={"error": "Conversation not found"})
        return messages
