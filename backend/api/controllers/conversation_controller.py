from fastapi import HTTPException

from config import Settings
from repositories.conversation_repository import ConversationRepository
from schemas.conversation import (
    ConversationDetailResponse,
    ConversationListItem,
    ConversationResponse,
    MessageResponse,
)


class ConversationController:
    def __init__(self, conversation_repository: ConversationRepository, settings: Settings) -> None:
        self.conversation_repository = conversation_repository
        self._settings = settings

    async def list_conversations(self) -> list[ConversationListItem]:
        rows = await self.conversation_repository.list_all()
        return [
            ConversationListItem(
                id=str(c.id),
                status=c.status,
                created_at=c.created_at,
                updated_at=c.updated_at,
            )
            for c in rows
        ]

    async def get_conversation_detail(self, conversation_id: str) -> ConversationDetailResponse:
        try:
            cid = int(conversation_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail={"error": "Invalid conversation_id"}) from exc

        conv = await self.conversation_repository.get_by_id(cid)
        if conv is None:
            raise HTTPException(status_code=404, detail={"error": "Conversation not found"})

        jira_key = await self.conversation_repository.get_latest_jira_ticket_id(cid)
        base = self._settings.jira_base_url.rstrip("/")
        jira_url = f"{base}/browse/{jira_key}" if jira_key else None

        return ConversationDetailResponse(
            id=str(conv.id),
            status=conv.status,
            created_at=conv.created_at,
            updated_at=conv.updated_at,
            jira_ticket_id=jira_key,
            jira_ticket_url=jira_url,
        )

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
