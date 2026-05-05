from datetime import datetime

from pydantic import BaseModel, Field


class ConversationResponse(BaseModel):
    id: str = Field(..., description="Conversation primary key as string")
    created_at: datetime


class ConversationListItem(BaseModel):
    """One row for GET /conversations (list all)."""

    id: str = Field(..., description="Conversation primary key as string")
    status: str
    created_at: datetime
    updated_at: datetime


class ConversationDetailResponse(BaseModel):
    """Metadata + ticket info for GET /conversations/{id}."""

    id: str
    status: str
    created_at: datetime
    updated_at: datetime
    ticket_id: str | None = None
    ticket_url: str | None = None


class MessageResponse(BaseModel):
    id: str = Field(..., description="Message primary key as string")
    conversation_id: str
    role: str
    content: str
    created_at: datetime
