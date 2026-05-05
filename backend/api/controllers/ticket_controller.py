from fastapi import HTTPException

from core.exceptions import JiraAPIError, ZendeskAPIError
from schemas.ticket import TicketCreateRequest, TicketCreateResponse
from services.ticket_service import TicketService


class TicketController:
    def __init__(self, ticket_service: TicketService) -> None:
        self._ticket_service = ticket_service

    async def create_ticket(self, body: TicketCreateRequest) -> TicketCreateResponse:
        try:
            return await self._ticket_service.create_ticket(body)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail={"error": str(exc)}) from exc
        except (JiraAPIError, ZendeskAPIError) as exc:
            raise HTTPException(status_code=502, detail={"error": exc.message}) from exc
