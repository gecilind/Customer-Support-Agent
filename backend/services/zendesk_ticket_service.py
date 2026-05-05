import base64
import logging

import httpx

from config import Settings
from core.exceptions import ZendeskAPIError
from schemas.zendesk_ticket import ZendeskTicketRequest, ZendeskTicketResponse

logger = logging.getLogger(__name__)


class ZendeskTicketService:
    def __init__(self, settings: Settings) -> None:
        self._subdomain = settings.zendesk_subdomain
        self._email = settings.zendesk_email
        self._api_token = settings.zendesk_api_token

    def _auth_header(self) -> str:
        raw = f"{self._email}/token:{self._api_token}"
        return "Basic " + base64.b64encode(raw.encode()).decode()

    async def create_ticket(self, request: ZendeskTicketRequest) -> ZendeskTicketResponse:
        url = f"https://{self._subdomain}.zendesk.com/api/v2/tickets.json"

        body = request.description
        if request.device_serial and request.device_serial.strip():
            body += f"\n\nDevice serial number: {request.device_serial.strip()}"

        payload = {
            "ticket": {
                "subject": request.summary,
                "comment": {"body": body},
                "priority": request.severity,
                "tags": [request.issue_type],
            }
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                resp = await client.post(
                    url,
                    json=payload,
                    headers={
                        "Authorization": self._auth_header(),
                        "Content-Type": "application/json",
                    },
                )
            except httpx.HTTPError as exc:
                raise ZendeskAPIError(f"Zendesk HTTP request failed: {exc}") from exc

        if resp.status_code not in (200, 201):
            raise ZendeskAPIError(
                f"Zendesk API returned {resp.status_code}: {resp.text[:500]}"
            )

        data = resp.json()
        ticket = data.get("ticket", {})
        ticket_id = ticket.get("id")
        ticket_url = f"https://{self._subdomain}.zendesk.com/agent/tickets/{ticket_id}"

        logger.info("[ZENDESK] Ticket created: %s (%s)", ticket_id, ticket_url)

        return ZendeskTicketResponse(
            zendesk_ticket_id=ticket_id,
            zendesk_ticket_url=ticket_url,
            issue_type=request.issue_type,
            severity=request.severity,
        )
