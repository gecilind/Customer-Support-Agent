from pydantic import BaseModel, Field


class TicketCreateRequest(BaseModel):
    conversation_id: int
    user_email: str
    device_serial: str | None = None
    issue_type: str  # "hardware_failure", "software_issue", etc.
    severity: str = Field(default="medium")  # "low", "medium", "high", "critical"
    summary: str
    description: str


class TicketCreateResponse(BaseModel):
    ticket_id: str
    ticket_url: str
    issue_type: str
    severity: str
