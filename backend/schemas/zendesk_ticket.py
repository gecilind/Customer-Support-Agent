from pydantic import BaseModel, Field


class ZendeskTicketRequest(BaseModel):
    conversation_id: int
    user_email: str
    device_serial: str | None = None
    issue_type: str
    severity: str = Field(default="medium")
    summary: str
    description: str


class ZendeskTicketResponse(BaseModel):
    zendesk_ticket_id: int
    zendesk_ticket_url: str
    issue_type: str
    severity: str
