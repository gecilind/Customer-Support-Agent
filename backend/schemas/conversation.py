from datetime import datetime

from pydantic import BaseModel, Field


class ConversationResponse(BaseModel):
    id: str = Field(..., description="Conversation primary key as string")
    created_at: datetime


class MessageResponse(BaseModel):
    id: str = Field(..., description="Message primary key as string")
    conversation_id: str
    role: str
    content: str
    created_at: datetime
