from schemas.ticket import TicketCreateRequest, TicketCreateResponse
from repositories.ticket_repository import TicketRepository


class TicketService:
    def __init__(self, ticket_repository: TicketRepository) -> None:
        self._ticket_repository = ticket_repository

    async def create_ticket(self, request: TicketCreateRequest) -> TicketCreateResponse:
        return await self._ticket_repository.create_jira_ticket(request)
