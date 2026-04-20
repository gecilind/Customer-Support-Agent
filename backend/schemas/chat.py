from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = Field(default=None)


class ChatResponse(BaseModel):
    conversation_id: str
    message: str
    confidence_tier: str
    sources: list[str]
    jira_ticket_url: str | None = None
