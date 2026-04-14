from fastapi import HTTPException
from starlette.responses import StreamingResponse

from schemas.chat import ChatRequest
from services.chat_service import ChatService


class ChatController:
    def __init__(self, chat_service: ChatService) -> None:
        self.chat_service = chat_service

    async def send_message(self, request: ChatRequest) -> StreamingResponse:
        try:
            return StreamingResponse(
                self.chat_service.handle_message_stream(request.message, request.conversation_id),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                },
            )
        except Exception:
            raise HTTPException(
                status_code=500,
                detail={"error": "Unable to complete chat request. Please try again."},
            ) from None
