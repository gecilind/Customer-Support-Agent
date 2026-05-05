import logging

from core.credential_redact import redact_ticket_field
from core.exceptions import ZendeskAPIError
from repositories.ticket_repository import TicketRepository
from schemas.ticket import TicketCreateRequest, TicketCreateResponse
from schemas.zendesk_ticket import ZendeskTicketRequest
from services.zendesk_ticket_service import ZendeskTicketService

logger = logging.getLogger(__name__)


class TicketService:
    def __init__(
        self,
        ticket_repository: TicketRepository,
        zendesk_ticket_service: ZendeskTicketService,
    ) -> None:
        self._ticket_repository = ticket_repository
        self._zendesk_ticket_service = zendesk_ticket_service

    async def create_ticket(self, request: TicketCreateRequest) -> TicketCreateResponse:
        summary = redact_ticket_field(request.summary.strip())[:500]
        description = redact_ticket_field(request.description.strip())[:8000]

        ds_raw = (request.device_serial or "").strip()
        parsed_serial: str | None
        if not ds_raw or ds_raw.lower() in ("null", "none"):
            parsed_serial = None
        else:
            parsed_serial = ds_raw

        redacted_request = TicketCreateRequest(
            conversation_id=request.conversation_id,
            user_email=request.user_email,
            device_serial=parsed_serial,
            issue_type=request.issue_type,
            severity=request.severity,
            summary=summary,
            description=description,
        )

        try:
            zendesk_request = ZendeskTicketRequest(
                conversation_id=redacted_request.conversation_id,
                user_email=redacted_request.user_email,
                device_serial=parsed_serial,
                issue_type=redacted_request.issue_type,
                severity=redacted_request.severity,
                summary=redacted_request.summary,
                description=redacted_request.description,
            )
            zresp = await self._zendesk_ticket_service.create_ticket(zendesk_request)
            await self._ticket_repository.save_ticket_record(
                conversation_id=redacted_request.conversation_id,
                ticket_id=str(zresp.zendesk_ticket_id),
                issue_type=redacted_request.issue_type,
                severity=redacted_request.severity,
                device_serial=parsed_serial,
            )
            return TicketCreateResponse(
                ticket_id=str(zresp.zendesk_ticket_id),
                ticket_url=zresp.zendesk_ticket_url,
                issue_type=zresp.issue_type,
                severity=zresp.severity,
            )
        except ZendeskAPIError as exc:
            logger.warning("[TICKET] Zendesk create failed, falling back to Jira: %s", exc)

        return await self._ticket_repository.create_jira_ticket(redacted_request)

    async def save_ticket_record(
        self,
        *,
        conversation_id: int,
        ticket_id: str,
        issue_type: str,
        severity: str,
        device_serial: str | None,
    ) -> None:
        await self._ticket_repository.save_ticket_record(
            conversation_id=conversation_id,
            ticket_id=ticket_id,
            issue_type=issue_type,
            severity=severity,
            device_serial=device_serial,
        )
