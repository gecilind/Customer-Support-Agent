import uuid
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.conversation import Conversation
from models.message import Message


class ConversationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_conversation(self) -> Conversation:
        """Create a new conversation. user_id/user_email use placeholders (DB NOT NULL)."""
        thread_id = str(uuid.uuid4())
        conv = Conversation(
            thread_id=thread_id,
            user_id="anonymous",
            user_email="anonymous@local",
            device_serial=None,
            status="active",
        )
        self.session.add(conv)
        await self.session.commit()
        await self.session.refresh(conv)
        return conv

    async def get_by_id(self, conversation_id: int) -> Conversation | None:
        stmt = select(Conversation).where(Conversation.id == conversation_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def add_message(
        self,
        conversation_id: int,
        role: str,
        content: str,
        confidence_tier: str | None = None,
    ) -> Message:
        # confidence_tier reserved for future DB column; not persisted until schema supports it
        _ = confidence_tier
        msg = Message(conversation_id=conversation_id, role=role, content=content)
        self.session.add(msg)
        await self.session.commit()
        await self.session.refresh(msg)
        return msg

    async def get_messages(self, conversation_id: int) -> Sequence[Message]:
        stmt = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.asc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()
