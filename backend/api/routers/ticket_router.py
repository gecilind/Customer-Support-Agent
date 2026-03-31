from fastapi import APIRouter, Depends

from api.controllers.ticket_controller import TicketController
from api.dependencies import get_ticket_controller
from schemas.ticket import TicketCreateRequest, TicketCreateResponse


router = APIRouter(tags=["tickets"])


@router.post("/create-ticket", response_model=TicketCreateResponse)
async def create_ticket(
    body: TicketCreateRequest,
    controller: TicketController = Depends(get_ticket_controller),
) -> TicketCreateResponse:
    return await controller.create_ticket(body)
