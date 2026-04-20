import asyncio
import base64
import json
import logging
import re
from datetime import datetime

import websockets
from fastapi import WebSocket, WebSocketDisconnect

from services.chat_service import ChatService

logger = logging.getLogger(__name__)

OPENAI_REALTIME_URL = "wss://api.openai.com/v1/realtime?model={model}"

# Session instructions that make the Realtime model act as a verbatim TTS relay.
# It is NOT used for AI reasoning — our chat_service handles that.
_RELAY_INSTRUCTIONS = (
    "You are a voice relay. When asked to say something, repeat it exactly as given, "
    "word for word, without any additions, omissions, or changes. "
    "Always speak in English regardless of the input language or accent."
)

# Regex: transcript is noise if it consists only of whitespace or punctuation
_NOISE_PATTERN = re.compile(r"^[\s.,!?;:\u2026\-\u2014\u2013\u00b7\*]+$")


def _now_ts() -> str:
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


class VoiceService:
    """
    Manages a single voice session:
      - Browser WebSocket  ↔  this relay  ↔  OpenAI Realtime API WebSocket

    Backend is the sole source of truth for mode (listening | processing | speaking).
    The frontend mirrors mode and gates the mic in the AudioWorklet; playback_drained
    ack from the FE unblocks Speaking → Listening.
    """

    def __init__(
        self,
        chat_service: ChatService,
        openai_api_key: str,
        realtime_model: str,
    ) -> None:
        self.chat_service = chat_service
        self.openai_api_key = openai_api_key
        self.realtime_model = realtime_model

    async def _transition(self, browser_ws: WebSocket, state: dict, new_mode: str) -> None:
        """Emit mode_end / mode_start and log a verifiable line on the server."""
        old_mode = state.get("mode")
        if old_mode == new_mode:
            return

        now_end = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        if old_mode:
            if state.get("mode_start"):
                logger.info(
                    "Mode: %s    Start: %s   End: %s",
                    old_mode.capitalize(),
                    state["mode_start"],
                    now_end,
                )
            try:
                await browser_ws.send_text(
                    json.dumps({"type": "mode_end", "mode": old_mode, "ts": now_end})
                )
            except Exception:
                return

        if old_mode == "speaking" and new_mode == "listening":
            logger.info("[ECHO GUARD] drain done, sleeping 0.8s")
            await asyncio.sleep(0.8)
            logger.info("[ECHO GUARD] cooldown done, transitioning")

        now_start = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        state["mode"] = new_mode
        state["mode_start"] = now_start
        try:
            await browser_ws.send_text(
                json.dumps({"type": "mode_start", "mode": new_mode, "ts": now_start})
            )
        except Exception:
            return

    async def run_session(self, browser_ws: WebSocket) -> None:
        """Open a Realtime API session and relay audio until the browser disconnects."""
        url = OPENAI_REALTIME_URL.format(model=self.realtime_model)
        headers = {
            "Authorization": f"Bearer {self.openai_api_key}",
            "OpenAI-Beta": "realtime=v1",
        }

        try:
            async with websockets.connect(url, additional_headers=headers) as openai_ws:
                await self._configure_session(openai_ws)

                state: dict = {
                    "conversation_id": None,
                    "cancelling": False,
                    "is_speaking": False,
                    "tts_pcm_bytes": 0,
                    "tts_response_in_flight": False,
                    "spoken_delta_for_response": False,
                    "playback_drained_event": asyncio.Event(),
                    "last_transcribed_item_id": None,
                }

                await self._send_initial_greeting(browser_ws, openai_ws, state)

                await asyncio.gather(
                    self._browser_to_openai(browser_ws, openai_ws, state),
                    self._openai_to_browser(openai_ws, browser_ws, state),
                    return_exceptions=True,
                )

        except WebSocketDisconnect:
            pass
        except Exception as exc:
            logger.error("[VOICE] Session-level error: %s", exc)
            try:
                await browser_ws.send_text(
                    json.dumps({"type": "error", "message": "Voice session error."})
                )
            except Exception:
                pass

    async def _configure_session(self, openai_ws) -> None:
        """Send session.update and wait for session.updated confirmation."""
        await openai_ws.send(json.dumps({
            "type": "session.update",
            "session": {
                "modalities": ["text", "audio"],
                "voice": "ash",
                "instructions": _RELAY_INSTRUCTIONS,
                "turn_detection": {
                    "type": "server_vad",
                    "threshold": 0.8,
                    "silence_duration_ms": 1500,
                    "prefix_padding_ms": 300,
                    "create_response": False,
                },
                "input_audio_format": "pcm16",
                "output_audio_format": "pcm16",
                "input_audio_transcription": {
                    "model": "whisper-1",
                    "language": "en",
                },
            },
        }))

        async for raw in openai_ws:
            evt = json.loads(raw)
            etype = evt.get("type")
            if etype == "session.updated":
                logger.info("[VOICE] Session configured.")
                break
            if etype == "error":
                logger.error("[VOICE] session.update error: %s", evt)
                break

    async def _send_initial_greeting(
        self, browser_ws: WebSocket, openai_ws, state: dict
    ) -> None:
        """Greeting uses the same mode machine: TTS deltas → speaking; audio.done → FE ack → listening."""
        try:
            response = await self.chat_service.handle_message(
                message="hello",
                conversation_id=None,
                is_voice=True,
            )
            state["conversation_id"] = response.conversation_id

            try:
                await browser_ws.send_text(
                    json.dumps({
                        "type": "transcript",
                        "role": "assistant",
                        "text": response.message,
                        "conversation_id": state.get("conversation_id"),
                    })
                )
            except Exception:
                pass

            await self._trigger_tts(openai_ws, response.message, state)

        except Exception as exc:
            logger.warning("[VOICE] Greeting failed: %s", exc)
            try:
                await self._transition(browser_ws, state, "listening")
            except Exception:
                pass

    async def _clear_input_audio_buffer(self, openai_ws) -> None:
        """Clear server input buffer so VAD cannot reuse audio for stray responses."""
        try:
            await openai_ws.send(json.dumps({"type": "input_audio_buffer.clear"}))
        except Exception:
            pass

    async def _trigger_tts(self, openai_ws, text: str, state: dict) -> None:
        state["tts_pcm_bytes"] = 0
        state["tts_response_in_flight"] = True
        state["spoken_delta_for_response"] = False
        await openai_ws.send(json.dumps({
            "type": "response.create",
            "response": {
                "modalities": ["text", "audio"],
                "instructions": (
                    f"Say the following text exactly as written, word for word, "
                    f"with no additions, changes, or commentary:\n\n{text}"
                ),
                "input": [],
            },
        }))

    async def _browser_to_openai(self, browser_ws: WebSocket, openai_ws, state: dict) -> None:
        """Forward binary PCM to OpenAI; handle playback_drained ack from the browser."""
        try:
            while True:
                try:
                    data = await browser_ws.receive()
                except WebSocketDisconnect:
                    break

                dtype = data.get("type", "")
                if dtype == "websocket.disconnect":
                    break

                text = data.get("text")
                if text:
                    try:
                        obj = json.loads(text)
                        if obj.get("type") == "playback_drained":
                            state["playback_drained_event"].set()
                    except json.JSONDecodeError:
                        pass
                    continue

                raw_bytes = data.get("bytes")
                if raw_bytes:
                    b64 = base64.b64encode(raw_bytes).decode()
                    await openai_ws.send(json.dumps({
                        "type": "input_audio_buffer.append",
                        "audio": b64,
                    }))
        except Exception:
            pass
        finally:
            try:
                await openai_ws.close()
            except Exception:
                pass

    async def _openai_to_browser(
        self, openai_ws, browser_ws: WebSocket, state: dict
    ) -> None:
        """Relay Realtime events; drive mode transitions and await FE playback ack."""
        try:
            async for raw in openai_ws:
                evt = json.loads(raw)
                etype = evt.get("type")

                if etype == "response.audio.delta":
                    if state["cancelling"]:
                        continue
                    audio_b64 = evt.get("delta", "")
                    if audio_b64:
                        if not state.get("spoken_delta_for_response"):
                            state["spoken_delta_for_response"] = True
                            state["is_speaking"] = True
                            await self._transition(browser_ws, state, "speaking")

                        audio_bytes = base64.b64decode(audio_b64)
                        state["tts_pcm_bytes"] = state.get("tts_pcm_bytes", 0) + len(
                            audio_bytes
                        )
                        try:
                            await browser_ws.send_bytes(audio_bytes)
                        except Exception:
                            return

                elif etype == "response.audio.done":
                    now_ts = _now_ts()
                    try:
                        await browser_ws.send_text(
                            json.dumps({"type": "tts_stream_ended", "ts": now_ts})
                        )
                    except Exception:
                        return
                    state["playback_drained_event"].clear()
                    await state["playback_drained_event"].wait()
                    state["tts_pcm_bytes"] = 0
                    if state.get("cancelling"):
                        continue
                    if state.get("mode") == "speaking":
                        state["is_speaking"] = False
                        await self._transition(browser_ws, state, "listening")

                elif etype == "response.done":
                    state["cancelling"] = False
                    state["tts_response_in_flight"] = False

                elif etype == "input_audio_buffer.speech_started":
                    # Barge-in: user spoke while AI audio is playing — cancel TTS and flush FE queue
                    if state.get("mode") == "speaking":
                        state["cancelling"] = True
                        await openai_ws.send(json.dumps({"type": "response.cancel"}))
                        try:
                            await browser_ws.send_text(json.dumps({"type": "flush_audio"}))
                        except Exception:
                            pass
                        await self._transition(browser_ws, state, "processing")

                elif etype == "input_audio_buffer.speech_stopped":
                    if state.get("cancelling"):
                        continue
                    if state.get("mode") == "listening":
                        await self._transition(browser_ws, state, "processing")
                        await self._clear_input_audio_buffer(openai_ws)

                elif etype == "conversation.item.input_audio_transcription.completed":
                    item_id = evt.get("item_id")
                    if item_id is None:
                        item = evt.get("item")
                        if isinstance(item, dict):
                            item_id = item.get("id")

                    if item_id and item_id == state.get("last_transcribed_item_id"):
                        logger.info("[VOICE] Duplicate transcription ignored (item_id=%s)", item_id)
                        continue

                    transcript = evt.get("transcript", "").strip()

                    if not transcript or _NOISE_PATTERN.fullmatch(transcript):
                        logger.info("[VOICE] Noise transcript ignored: %r", transcript)
                        continue

                    logger.info("[VOICE] Transcript: %r", transcript)

                    try:
                        await browser_ws.send_text(
                            json.dumps({
                                "type": "transcript",
                                "role": "user",
                                "text": transcript,
                                "conversation_id": state.get("conversation_id"),
                            })
                        )
                    except Exception:
                        pass

                    await self._clear_input_audio_buffer(openai_ws)

                    if state.get("mode") == "listening":
                        await self._transition(browser_ws, state, "processing")

                    state["cancelling"] = True
                    if state.get("tts_response_in_flight") or state.get("mode") == "speaking":
                        await openai_ws.send(json.dumps({"type": "response.cancel"}))
                        await asyncio.sleep(0.05)

                    chat_response = None
                    try:
                        chat_response = await self.chat_service.handle_message(
                            message=transcript,
                            conversation_id=state["conversation_id"],
                            is_voice=True,
                        )
                        state["conversation_id"] = chat_response.conversation_id
                        response_text = chat_response.message
                    except Exception as exc:
                        logger.error("[VOICE] chat_service error: %s", exc)
                        response_text = (
                            "I'm sorry, I encountered an error. Please try again."
                        )

                    state["cancelling"] = False
                    if item_id:
                        state["last_transcribed_item_id"] = item_id

                    try:
                        await browser_ws.send_text(
                            json.dumps({
                                "type": "transcript",
                                "role": "assistant",
                                "text": response_text,
                                "conversation_id": state.get("conversation_id"),
                            })
                        )
                    except Exception:
                        pass

                    ticket_url = (
                        chat_response.jira_ticket_url
                        if chat_response is not None
                        else None
                    )
                    if ticket_url:
                        try:
                            await browser_ws.send_text(
                                json.dumps({
                                    "type": "ticket_created",
                                    "url": ticket_url,
                                })
                            )
                        except Exception:
                            pass

                    await self._trigger_tts(openai_ws, response_text, state)

                elif etype == "error":
                    err = evt.get("error") or {}
                    if err.get("code") == "response_cancel_not_active":
                        logger.debug("[VOICE] Realtime API (benign): %s", evt)
                    else:
                        logger.error("[VOICE] Realtime API error: %s", evt)

        except Exception as exc:
            logger.error("[VOICE] openai_to_browser error: %s", exc)
