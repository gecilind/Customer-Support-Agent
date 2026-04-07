import base64
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from config import Settings
from core.exceptions import JiraAPIError
from models.conversation import Conversation
from models.ticket import Ticket
from schemas.ticket import TicketCreateRequest, TicketCreateResponse


def _severity_to_jira_priority(severity: str) -> str:
    s = severity.lower().strip()
    mapping = {
        "critical": "Highest",
        "high": "High",
        "medium": "Medium",
        "low": "Low",
    }
    return mapping.get(s, "Medium")


def _jira_description_adf(request: TicketCreateRequest) -> dict[str, Any]:
    content: list[dict[str, Any]] = [
        {
            "type": "paragraph",
            "content": [{"type": "text", "text": request.description}],
        }
    ]
    if request.device_serial is not None:
        serial = request.device_serial.strip()
        if serial:
            content.append(
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": f"Device serial number: {serial}"}],
                }
            )
    return {"type": "doc", "version": 1, "content": content}


def _jira_issue_payload(request: TicketCreateRequest, settings: Settings) -> dict[str, Any]:
    return {
        "fields": {
            "project": {"key": settings.jira_project_key},
            "issuetype": {"name": "Task"},
            "priority": {"name": _severity_to_jira_priority(request.severity)},
            "summary": request.summary,
            "description": _jira_description_adf(request),
            "labels": [request.issue_type],
        }
    }


class TicketRepository:
    def __init__(
        self,
        http_client: httpx.AsyncClient,
        session: AsyncSession,
        settings: Settings,
    ) -> None:
        self._http = http_client
        self._session = session
        self._settings = settings

    async def create_jira_ticket(self, request: TicketCreateRequest) -> TicketCreateResponse:
        result = await self._session.execute(
            select(Conversation.id).where(Conversation.id == request.conversation_id)
        )
        if result.scalar_one_or_none() is None:
            raise ValueError(f"Conversation {request.conversation_id} not found")

        base = self._settings.jira_base_url.rstrip("/")
        url = f"{base}/rest/api/3/issue"
        credentials = base64.b64encode(
            f"{self._settings.jira_email}:{self._settings.jira_api_token}".encode()
        ).decode()
        headers = {
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        payload = _jira_issue_payload(request, self._settings)

        try:
            response = await self._http.post(url, json=payload, headers=headers)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text if exc.response else str(exc)
            raise JiraAPIError(f"Jira API error ({exc.response.status_code if exc.response else '?'}): {detail}") from exc
        except httpx.RequestError as exc:
            raise JiraAPIError(f"Jira request failed: {exc}") from exc

        try:
            body = response.json()
            key = body["key"]
        except (KeyError, ValueError) as exc:
            raise JiraAPIError(f"Unexpected Jira response: {response.text}") from exc

        ticket = Ticket(
            conversation_id=request.conversation_id,
            jira_ticket_id=key,
            issue_type=request.issue_type,
            severity=request.severity,
            device_serial=request.device_serial,
        )
        self._session.add(ticket)
        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise ValueError("Could not save ticket reference (invalid conversation or duplicate Jira key).") from exc

        jira_ticket_url = f"{base}/browse/{key}"
        return TicketCreateResponse(
            jira_ticket_id=key,
            jira_ticket_url=jira_ticket_url,
            issue_type=request.issue_type,
            severity=request.severity,
        )
