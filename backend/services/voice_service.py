import asyncio
import base64
import json
import logging
import re
import time

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

# Realtime PCM16 output is mono; match frontend playback rate for drain timing.
_TTS_OUTPUT_SAMPLE_RATE = 24_000
# Minimum post-audio.done wait (covers scheduling / jitter).
_PLAYBACK_DRAIN_MIN_S = 0.8
# Extra slack after estimated PCM duration so UI stays "speaking" until playback likely finished.
_PLAYBACK_DRAIN_PAD_S = 0.35


class VoiceService:
    """
    Manages a single voice session:
      - Browser WebSocket  ↔  this relay  ↔  OpenAI Realtime API WebSocket

    Audio flow:
      Browser PCM16 16 kHz → input_audio_buffer.append → OpenAI VAD + STT
      transcription → chat_service.handle_message() → response text
      response text → response.create (TTS) → response.audio.delta → Browser

    Text frames sent to the browser carry state signals:
      {"type": "state", "state": "listening"|"processing"|"speaking"}
      {"type": "error",  "message": "..."}
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

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    async def run_session(self, browser_ws: WebSocket) -> None:
        """Open a Realtime API session and relay audio until the browser disconnects."""
        url = OPENAI_REALTIME_URL.format(model=self.realtime_model)
        headers = {
            "Authorization": f"Bearer {self.openai_api_key}",
            "OpenAI-Beta": "realtime=v1",
        }

        try:
            async with websockets.connect(url, additional_headers=headers) as openai_ws:
                # 1. Configure the session (VAD, STT, voice)
                await self._configure_session(openai_ws)

                # 2. Shared mutable state (single asyncio thread — no locks needed)
                state: dict = {
                    "conversation_id": None,
                    "cancelling": False,
                    "is_speaking": False,
                    "tts_pcm_bytes": 0,
                }

                try:
                    await browser_ws.send_text(
                        json.dumps({"type": "state", "state": "listening"})
                    )
                except Exception:
                    pass

                # 3. Get initial greeting from chat_service → TTS it
                await self._send_initial_greeting(browser_ws, openai_ws, state)

                # 4. Run bidirectional relay concurrently
                await asyncio.gather(
                    self._browser_to_openai(browser_ws, openai_ws),
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

    # ------------------------------------------------------------------
    # Session configuration
    # ------------------------------------------------------------------

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
                    "threshold": 0.7,
                    "silence_duration_ms": 1500,
                    "prefix_padding_ms": 300,
                },
                "input_audio_format": "pcm16",
                "output_audio_format": "pcm16",
                "input_audio_transcription": {
                    "model": "whisper-1",
                    "language": "en",
                },
            },
        }))

        # Consume events until session is confirmed or an error occurs
        async for raw in openai_ws:
            evt = json.loads(raw)
            etype = evt.get("type")
            if etype == "session.updated":
                logger.info("[VOICE] Session configured.")
                break
            if etype == "error":
                logger.error("[VOICE] session.update error: %s", evt)
                break

    # ------------------------------------------------------------------
    # Initial greeting
    # ------------------------------------------------------------------

    async def _send_initial_greeting(
        self, browser_ws: WebSocket, openai_ws, state: dict
    ) -> None:
        """
        Call chat_service with 'hello' to get the AI greeting, then trigger TTS.
        The greeting audio is consumed by the main _openai_to_browser loop so
        we only fire off the response.create here without waiting for audio done.
        """
        try:
            response = await self.chat_service.handle_message(
                message="hello",
                conversation_id=None,
                is_voice=True,
            )
            state["conversation_id"] = response.conversation_id

            await self._trigger_tts(openai_ws, response.message, state)

        except Exception as exc:
            logger.warning("[VOICE] Greeting failed: %s", exc)
            # Let the user start the conversation themselves
            await browser_ws.send_text(json.dumps({"type": "state", "state": "listening"}))

    # ------------------------------------------------------------------
    # TTS helper
    # ------------------------------------------------------------------

    async def _trigger_tts(self, openai_ws, text: str, state: dict) -> None:
        """
        Ask the Realtime API to speak `text` verbatim.

        We use response.create with an empty input array and per-response
        instructions that contain the text to speak. This bypasses the
        Realtime model's own reasoning and uses it purely as a TTS engine.
        """
        state["tts_pcm_bytes"] = 0
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

    # ------------------------------------------------------------------
    # Browser → OpenAI relay
    # ------------------------------------------------------------------

    async def _browser_to_openai(self, browser_ws: WebSocket, openai_ws) -> None:
        """
        Forward binary PCM16 16 kHz mono frames from the browser to OpenAI
        as base64-encoded input_audio_buffer.append events.
        """
        try:
            while True:
                try:
                    data = await browser_ws.receive()
                except WebSocketDisconnect:
                    break

                dtype = data.get("type", "")
                if dtype == "websocket.disconnect":
                    break

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
            # Closing openai_ws causes _openai_to_browser to exit its async-for loop
            try:
                await openai_ws.close()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # OpenAI → Browser relay + VAD/transcription handling
    # ------------------------------------------------------------------

    async def _openai_to_browser(
        self, openai_ws, browser_ws: WebSocket, state: dict
    ) -> None:
        """
        Handle all events from the Realtime API:
        - audio.delta  → relay PCM16 bytes to browser
        - response.audio.done → drain (min + estimated PCM play time), then "listening"
        - input_audio_buffer.speech_started → state "listening" (when not speaking)
        - transcription.completed → chat_service → TTS
        """
        try:
            last_speech_started: float = 0.0
            async for raw in openai_ws:
                evt = json.loads(raw)
                etype = evt.get("type")

                # ── Relay audio to browser ──────────────────────────────
                if etype == "response.audio.delta":
                    if state["cancelling"]:
                        continue
                    audio_b64 = evt.get("delta", "")
                    if audio_b64:
                        if not state["is_speaking"]:
                            state["is_speaking"] = True
                            state["tts_pcm_bytes"] = 0
                            try:
                                await browser_ws.send_text(
                                    json.dumps({"type": "state", "state": "speaking"})
                                )
                            except Exception:
                                return
                        audio_bytes = base64.b64decode(audio_b64)
                        state["tts_pcm_bytes"] = state.get("tts_pcm_bytes", 0) + len(
                            audio_bytes
                        )
                        try:
                            await browser_ws.send_bytes(audio_bytes)
                        except Exception:
                            return

                # ── Audio stream finished → transition to listening ────
                elif etype == "response.audio.done":
                    if not state["cancelling"]:
                        pcm_bytes = max(0, state.get("tts_pcm_bytes", 0))
                        est_playback_s = (pcm_bytes / 2) / _TTS_OUTPUT_SAMPLE_RATE
                        drain_s = max(
                            _PLAYBACK_DRAIN_MIN_S,
                            est_playback_s + _PLAYBACK_DRAIN_PAD_S,
                        )
                        # Keep is_speaking True until after drain so echo VAD cannot
                        # push "listening" while the browser is still playing queued PCM.
                        await asyncio.sleep(drain_s)
                        if state["cancelling"]:
                            continue
                        state["is_speaking"] = False
                        state["tts_pcm_bytes"] = 0
                        try:
                            await browser_ws.send_text(
                                json.dumps({"type": "state", "state": "listening"})
                            )
                        except Exception:
                            return

                elif etype == "response.done":
                    state["cancelling"] = False

                # ── User started speaking ───────────────────────────────
                elif etype == "input_audio_buffer.speech_started":
                    now = time.monotonic()
                    if not state.get("is_speaking", False) and (now - last_speech_started) > 1.0:
                        last_speech_started = now
                        try:
                            await browser_ws.send_text(
                                json.dumps({"type": "state", "state": "listening"})
                            )
                        except Exception:
                            return

                # ── User speech transcribed ─────────────────────────────
                elif etype == "conversation.item.input_audio_transcription.completed":
                    transcript = evt.get("transcript", "").strip()

                    # STT failsafe: ignore empty / noise / punctuation-only transcripts
                    if not transcript or _NOISE_PATTERN.fullmatch(transcript):
                        logger.info("[VOICE] Noise transcript ignored: %r", transcript)
                        continue

                    logger.info("[VOICE] Transcript: %r", transcript)

                    state["cancelling"] = True
                    try:
                        await browser_ws.send_text(
                            json.dumps({"type": "state", "state": "processing"})
                        )
                    except Exception:
                        return

                    await openai_ws.send(json.dumps({"type": "response.cancel"}))
                    await asyncio.sleep(0.05)

                    # ── Call our AI pipeline ────────────────────────────
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

                    # ── Trigger TTS of our response ─────────────────────
                    state["cancelling"] = False
                    await self._trigger_tts(openai_ws, response_text, state)

                # ── Log Realtime API errors ─────────────────────────────
                elif etype == "error":
                    logger.error("[VOICE] Realtime API error: %s", evt)

        except Exception as exc:
            logger.error("[VOICE] openai_to_browser error: %s", exc)
