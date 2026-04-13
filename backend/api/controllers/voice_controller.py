import logging

from fastapi import WebSocket, WebSocketDisconnect

from services.voice_service import VoiceService

logger = logging.getLogger(__name__)


class VoiceController:
    """WebSocket lifecycle handler for /voice-relay."""

    def __init__(self, voice_service: VoiceService) -> None:
        self.voice_service = voice_service

    async def handle_connection(self, websocket: WebSocket) -> None:
        await websocket.accept()
        logger.info("[VOICE] Browser connected.")
        try:
            await self.voice_service.run_session(websocket)
        except WebSocketDisconnect:
            logger.info("[VOICE] Browser disconnected.")
        except Exception as exc:
            logger.error("[VOICE] Unhandled controller error: %s", exc)
        finally:
            try:
                await websocket.close()
            except Exception:
                pass
            logger.info("[VOICE] Session closed.")
