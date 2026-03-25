from fastapi import HTTPException

from repositories.conversation_repository import ConversationRepository
from schemas.conversation import ConversationResponse, MessageResponse


class ConversationController:
    def __init__(self, conversation_repository: ConversationRepository) -> None:
        self.conversation_repository = conversation_repository

    async def create_conversation(self) -> ConversationResponse:
        conv = await self.conversation_repository.create_conversation()
        return ConversationResponse(id=str(conv.id), created_at=conv.created_at)

    async def get_messages(self, conversation_id: str) -> list[MessageResponse]:
        try:
            cid = int(conversation_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail={"error": "Invalid conversation_id"}) from exc

        conv = await self.conversation_repository.get_by_id(cid)
        if conv is None:
            raise HTTPException(status_code=404, detail={"error": "Conversation not found"})

        rows = await self.conversation_repository.get_messages(cid)
        return [
            MessageResponse(
                id=str(m.id),
                conversation_id=str(m.conversation_id),
                role=m.role,
                content=m.content,
                created_at=m.created_at,
            )
            for m in rows
        ]
