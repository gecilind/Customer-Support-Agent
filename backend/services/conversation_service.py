from config import Settings
from repositories.conversation_repository import ConversationRepository
from schemas.conversation import (
    ConversationDetailResponse,
    ConversationListItem,
    ConversationResponse,
    MessageResponse,
)


class ConversationService:
    def __init__(self, conversation_repository: ConversationRepository, settings: Settings) -> None:
        self._conversation_repository = conversation_repository
        self._settings = settings

    async def list_conversations(self) -> list[ConversationListItem]:
        rows = await self._conversation_repository.list_all()
        return [
            ConversationListItem(
                id=str(c.id),
                status=c.status,
                created_at=c.created_at,
                updated_at=c.updated_at,
            )
            for c in rows
        ]

    async def get_conversation_detail(self, conversation_id: int) -> ConversationDetailResponse | None:
        conv = await self._conversation_repository.get_by_id(conversation_id)
        if conv is None:
            return None

        ticket_key = await self._conversation_repository.get_latest_ticket_id(conversation_id)
        ticket_url: str | None = None
        if ticket_key:
            if ticket_key.isdigit():
                ticket_url = f"https://{self._settings.zendesk_subdomain}.zendesk.com/agent/tickets/{ticket_key}"
            else:
                base = self._settings.jira_base_url.rstrip("/")
                ticket_url = f"{base}/browse/{ticket_key}"

        return ConversationDetailResponse(
            id=str(conv.id),
            status=conv.status,
            created_at=conv.created_at,
            updated_at=conv.updated_at,
            ticket_id=ticket_key,
            ticket_url=ticket_url,
        )

    async def create_conversation(self) -> ConversationResponse:
        conv = await self._conversation_repository.create_conversation()
        return ConversationResponse(id=str(conv.id), created_at=conv.created_at)

    async def get_messages(self, conversation_id: int) -> list[MessageResponse] | None:
        conv = await self._conversation_repository.get_by_id(conversation_id)
        if conv is None:
            return None

        rows = await self._conversation_repository.get_messages(conversation_id)
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
