from fastapi import HTTPException

from schemas.chat import ChatRequest, ChatResponse
from services.chat_service import ChatService


class ChatController:
    def __init__(self, chat_service: ChatService) -> None:
        self.chat_service = chat_service

    async def send_message(self, request: ChatRequest) -> ChatResponse:
        try:
            return await self.chat_service.handle_message(request.message, request.conversation_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail={"error": str(exc)}) from exc
        except Exception:
            raise HTTPException(
                status_code=500,
                detail={"error": "Unable to complete chat request. Please try again."},
            ) from None
