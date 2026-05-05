import uuid
from datetime import datetime, timezone
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.conversation import Conversation
from models.message import Message
from models.ticket import Ticket


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

    async def list_all(self) -> Sequence[Conversation]:
        stmt = select(Conversation).order_by(Conversation.created_at.desc())
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_latest_ticket_id(self, conversation_id: int) -> str | None:
        stmt = (
            select(Ticket.ticket_id)
            .where(Ticket.conversation_id == conversation_id)
            .order_by(Ticket.created_at.desc())
            .limit(1)
        )
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

    async def update_status(self, conversation_id: int, status: str) -> None:
        conv = await self.get_by_id(conversation_id)
        if conv is None:
            return
        conv.status = status
        conv.updated_at = datetime.now(timezone.utc)
        await self.session.commit()

    async def update_device_serial(self, conversation_id: int, device_serial: str) -> None:
        """Update the device serial on a conversation after AI collects it."""
        conv = await self.get_by_id(conversation_id)
        if conv is None:
            return
        conv.device_serial = device_serial
        conv.updated_at = datetime.now(timezone.utc)
        await self.session.commit()
