import React, { useCallback, useEffect, useRef, useState } from 'react';
import { ArrowLeft, Mic, Loader2, PhoneOff, Volume2 } from 'lucide-react';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type VoiceState = 'connecting' | 'listening' | 'processing' | 'speaking' | 'error';

interface Props {
  onBack: () => void;
}

/** Browser console: same prefix as backend logs for cross-checking sync. */
function clientVoiceSync(
  sessionT0Ms: { current: number },
  event: string,
  extra?: Record<string, unknown>,
) {
  if (!sessionT0Ms.current) sessionT0Ms.current = performance.now();
  const elapsed_ms = Math.round((performance.now() - sessionT0Ms.current) * 100) / 100;
  console.info(
    '[VOICE_SYNC]',
    JSON.stringify({
      layer: 'frontend',
      event,
      elapsed_ms,
      wall_ts_ms: Date.now(),
      ...extra,
    }),
  );
}

// ---------------------------------------------------------------------------
// Audio helpers
// ---------------------------------------------------------------------------

/**
 * Convert PCM16 little-endian bytes (OpenAI TTS output at 24 kHz) to a
 * Float32Array so we can feed it into an AudioBufferSourceNode.
 */
function pcm16BytesToFloat32(buffer: ArrayBuffer): Float32Array {
  const int16 = new Int16Array(buffer);
  const float32 = new Float32Array(int16.length);
  for (let i = 0; i < int16.length; i++) {
    float32[i] = int16[i] / 32_768;
  }
  return float32;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function VoiceInterface({ onBack }: Props) {
  const [voiceState, setVoiceState] = useState<VoiceState>('connecting');
  const [errorMsg, setErrorMsg] = useState<string>('');
  const stateRef = useRef<VoiceState>('connecting');

  // Refs so closures in event handlers always see current values
  const wsRef = useRef<WebSocket | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const workletNodeRef = useRef<AudioWorkletNode | null>(null);
  const micStreamRef = useRef<MediaStream | null>(null);
  // Tracks the next time we should schedule audio playback to avoid gaps
  const nextPlayTimeRef = useRef<number>(0);
  const voiceSessionT0Ref = useRef<number>(0);
  const playbackPendingRef = useRef(0);

  // ------------------------------------------------------------------
  // Playback: schedule a PCM16 chunk as an AudioBufferSourceNode
  // ------------------------------------------------------------------
  const playAudioChunk = useCallback((bytes: ArrayBuffer) => {
    // Half-duplex: do not play assistant audio unless UI is in speaking (server sends
    // state before PCM; drops stray chunks if state desynced).
    if (stateRef.current !== 'speaking') {
      return;
    }
    const ctx = audioCtxRef.current;
    if (!ctx) return;
    if (ctx.state === 'suspended') {
      void ctx.resume();
    }

    const float32 = pcm16BytesToFloat32(bytes);
    // Create a buffer at the TTS output rate (OpenAI Realtime API: 24 kHz).
    // The AudioContext will automatically resample to its own output rate.
    const audioBuf = ctx.createBuffer(1, float32.length, 24_000);
    audioBuf.getChannelData(0).set(float32);

    const source = ctx.createBufferSource();
    source.buffer = audioBuf;
    source.connect(ctx.destination);

    const now = ctx.currentTime;
    const startAt = Math.max(now, nextPlayTimeRef.current);
    source.start(startAt);
    nextPlayTimeRef.current = startAt + audioBuf.duration;

    playbackPendingRef.current += 1;
    const pendingAfter = playbackPendingRef.current;
    if (pendingAfter === 1) {
      clientVoiceSync(voiceSessionT0Ref, 'user_listening_playback_first_chunk', {
        samples: float32.length,
        scheduled_end_audio_time: startAt + audioBuf.duration,
        ui_state: stateRef.current,
      });
    }
    source.onended = () => {
      playbackPendingRef.current -= 1;
      if (playbackPendingRef.current <= 0) {
        playbackPendingRef.current = 0;
        clientVoiceSync(voiceSessionT0Ref, 'user_listening_playback_queue_empty', {
          ui_state: stateRef.current,
        });
      }
    };
  }, []);

  // ------------------------------------------------------------------
  // Tear-down: close WebSocket + stop mic + suspend audio context
  // ------------------------------------------------------------------
  const teardown = useCallback(() => {
    try { wsRef.current?.close(); } catch { /* ignore */ }
    try { workletNodeRef.current?.disconnect(); } catch { /* ignore */ }
    micStreamRef.current?.getTracks().forEach((t) => t.stop());
    audioCtxRef.current?.suspend().catch(() => { /* ignore */ });
  }, []);

  const handleBack = useCallback(() => {
    teardown();
    onBack();
  }, [teardown, onBack]);

  // ------------------------------------------------------------------
  // Main setup: mic → worklet → WebSocket  +  WebSocket → speaker
  // ------------------------------------------------------------------
  useEffect(() => {
    let cancelled = false;

    const setup = async () => {
      // 1. Request microphone permission
      let stream: MediaStream;
      try {
        stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
      } catch {
        if (!cancelled) {
          setErrorMsg('Microphone access denied. Please allow microphone and reload.');
          setVoiceState('error');
        }
        return;
      }
      if (cancelled) { stream.getTracks().forEach((t) => t.stop()); return; }
      micStreamRef.current = stream;

      // 2. Create AudioContext
      const ctx = new AudioContext();
      audioCtxRef.current = ctx;
      // Browsers start AudioContext suspended until resumed (autoplay policy).
      try {
        await ctx.resume();
      } catch {
        /* ignore */
      }

      // 3. Open WebSocket early so backend state frames are not missed while worklet loads.
      const base = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/+$/, '');
      const wsUrl = `${base.replace(/^http/, 'ws')}/voice-relay`;
      const ws = new WebSocket(wsUrl);
      ws.binaryType = 'arraybuffer';
      wsRef.current = ws;

      ws.onopen = () => {
        voiceSessionT0Ref.current = performance.now();
        nextPlayTimeRef.current = 0;
        playbackPendingRef.current = 0;
        clientVoiceSync(voiceSessionT0Ref, 'client_ws_open', { url: wsUrl });
      };

      ws.onmessage = (evt: MessageEvent) => {
        if (typeof evt.data === 'string') {
          try {
            const msg = JSON.parse(evt.data) as {
              type: string;
              state?: VoiceState;
              message?: string;
              event?: string;
              elapsed_ms?: number;
              wall_ts_ms?: number;
            };
            if (msg.type === 'voice_sync' && msg.event) {
              console.info(
                '[VOICE_SYNC]',
                JSON.stringify({
                  layer: 'frontend',
                  source: 'ws_relay',
                  event: msg.event,
                  elapsed_ms: msg.elapsed_ms,
                  wall_ts_ms: msg.wall_ts_ms,
                  ...Object.fromEntries(
                    Object.entries(msg).filter(
                      ([k]) => !['type', 'event', 'elapsed_ms', 'wall_ts_ms'].includes(k),
                    ),
                  ),
                }),
              );
              return;
            }
            if (msg.type === 'state' && msg.state) {
              if (!cancelled) {
                const prev = stateRef.current;
                const next = msg.state;
                if (prev !== next) {
                  clientVoiceSync(voiceSessionT0Ref, 'ui_state_transition', { from: prev, to: next });
                }
                setVoiceState(next);
                stateRef.current = next;
              }
            } else if (msg.type === 'error') {
              if (!cancelled) {
                setErrorMsg(msg.message ?? 'An error occurred.');
                setVoiceState('error');
              }
            }
          } catch { /* non-JSON text, ignore */ }
        } else if (evt.data instanceof ArrayBuffer && evt.data.byteLength > 0) {
          playAudioChunk(evt.data);
        }
      };

      ws.onerror = () => {
        if (!cancelled) {
          setErrorMsg('Connection to voice service failed.');
          setVoiceState('error');
        }
      };

      ws.onclose = () => {
        if (!cancelled && voiceState !== 'error') {
          // Backend closed — silently return to selection
        }
      };

      // 4. Load the PCM worklet
      try {
        // Vite serves the TypeScript source at its URL during dev;
        // in production the file is compiled and content-hashed.
        const workletUrl = new URL('../audio/pcm-worklet.ts', import.meta.url);
        await ctx.audioWorklet.addModule(workletUrl);
      } catch {
        // Fallback: inline blob worklet (works when Vite ?url isn't available)
        const code = `
          class PCMProcessor extends AudioWorkletProcessor {
            process(inputs) {
              const ch = inputs[0]?.[0];
              if (!ch || !ch.length) return true;
              const ratio = sampleRate / 16000;
              const outLen = Math.floor(ch.length / ratio);
              if (!outLen) return true;
              const pcm = new Int16Array(outLen);
              for (let i = 0; i < outLen; i++) {
                const s = ch[Math.floor(i * ratio)];
                pcm[i] = Math.max(-32768, Math.min(32767, Math.round(s * 32767)));
              }
              this.port.postMessage(pcm.buffer, [pcm.buffer]);
              return true;
            }
          }
          registerProcessor('pcm-processor', PCMProcessor);
        `;
        const blob = new Blob([code], { type: 'application/javascript' });
        await ctx.audioWorklet.addModule(URL.createObjectURL(blob));
      }

      if (cancelled) { stream.getTracks().forEach((t) => t.stop()); return; }

      // 5. Wire mic → worklet
      const source = ctx.createMediaStreamSource(stream);
      const workletNode = new AudioWorkletNode(ctx, 'pcm-processor');
      workletNodeRef.current = workletNode;
      source.connect(workletNode);
      // No output: worklet posts messages; we don't route audio to speakers

      // 6. Forward PCM16 frames from worklet → WebSocket only in true "user may talk" window:
      //    half-duplex — not while assistant audio is playing locally (avoids echo / VAD junk).
      workletNode.port.onmessage = (evt: MessageEvent<ArrayBuffer>) => {
        if (ws.readyState !== WebSocket.OPEN) return;
        if (stateRef.current !== 'listening') return;
        const ctxMic = audioCtxRef.current;
        const tailDone =
          playbackPendingRef.current === 0 &&
          (!ctxMic || ctxMic.currentTime >= nextPlayTimeRef.current - 0.04);
        if (!tailDone) return;
        ws.send(evt.data);
      };
    };

    void setup();

    return () => {
      cancelled = true;
      teardown();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ------------------------------------------------------------------
  // Visual state rendering helpers
  // ------------------------------------------------------------------

  const stateConfig: Record<
    VoiceState,
    { label: string; color: string; icon: React.ReactNode; hint?: string }
  > = {
    connecting: {
      label: 'Connecting…',
      color: 'text-slate-500',
      icon: <Loader2 size={52} className="animate-spin text-slate-400" strokeWidth={1.5} />,
    },
    listening: {
      label: 'Listening',
      color: 'text-emerald-600',
      icon: (
        <div className="relative flex items-center justify-center">
          {/* Pulsing rings */}
          <span className="absolute inline-flex h-24 w-24 rounded-full bg-emerald-100 opacity-75 animate-ping" />
          <span className="absolute inline-flex h-20 w-20 rounded-full bg-emerald-50 opacity-50 animate-ping [animation-delay:0.3s]" />
          <div className="relative z-10 p-5 rounded-full bg-emerald-100 text-emerald-700">
            <Mic size={36} strokeWidth={2} />
          </div>
        </div>
      ),
    },
    processing: {
      label: 'Processing…',
      color: 'text-amber-600',
      icon: (
        <div className="p-5 rounded-full bg-amber-50 text-amber-600">
          <Loader2 size={36} className="animate-spin" strokeWidth={2} />
        </div>
      ),
      hint: 'Heard you — fetching context and drafting a reply. Mic is off until the assistant speaks.',
    },
    speaking: {
      label: 'AI Speaking',
      color: 'text-blue-600',
      hint: 'Your mic is off until playback ends and the screen returns to Listening.',
      icon: (
        <div className="relative flex items-center justify-center">
          <div className="p-5 rounded-full bg-blue-50 text-blue-600">
            <Volume2 size={36} strokeWidth={2} />
          </div>
          {/* Animated sound bars */}
          <div className="absolute -bottom-6 flex items-end gap-1">
            {[12, 20, 16, 24, 14, 20, 10].map((h, i) => (
              <div
                key={i}
                className="w-1 rounded-full bg-blue-400 animate-pulse"
                style={{
                  height: `${h}px`,
                  animationDelay: `${i * 0.1}s`,
                  animationDuration: '0.8s',
                }}
              />
            ))}
          </div>
        </div>
      ),
    },
    error: {
      label: 'Error',
      color: 'text-red-600',
      icon: (
        <div className="p-5 rounded-full bg-red-50 text-red-500">
          <Mic size={36} strokeWidth={2} />
        </div>
      ),
    },
  };

  const cfg = stateConfig[voiceState];

  // ------------------------------------------------------------------
  // Render
  // ------------------------------------------------------------------
  return (
    <div className="flex flex-col h-full bg-white animate-in fade-in duration-300">
      {/* Header */}
      <div className="flex items-center gap-3 px-4 py-3 border-b border-slate-200 shrink-0">
        <button
          type="button"
          onClick={handleBack}
          className="p-1.5 rounded-sm text-slate-500 hover:text-slate-900 hover:bg-slate-100 transition-colors focus:outline-none focus:ring-2 focus:ring-blue-900"
          aria-label="Back to selection"
        >
          <ArrowLeft size={18} strokeWidth={2} />
        </button>
        <div>
          <h2 className="text-sm font-semibold text-slate-900 leading-tight">Voice Agent</h2>
          <p className="text-[11px] text-slate-500 leading-tight">Infleet AI Support</p>
        </div>
      </div>

      {/* Main area */}
      <div className="flex flex-col flex-1 items-center justify-center gap-10 px-8">
        {/* Animated icon */}
        <div className="flex items-center justify-center min-h-[100px]">
          {cfg.icon}
        </div>

        {/* State label */}
        <div className="text-center">
          <p className={`text-lg font-semibold ${cfg.color}`}>{cfg.label}</p>
          {cfg.hint && (
            <p className="text-xs text-slate-500 mt-1 max-w-[280px] mx-auto leading-snug">{cfg.hint}</p>
          )}
          {voiceState === 'listening' && (
            <p className="text-xs text-slate-400 mt-1">Speak now — AI will respond when you pause</p>
          )}
          {voiceState === 'error' && (
            <p className="text-xs text-red-500 mt-1 max-w-[260px] text-center">{errorMsg}</p>
          )}
        </div>

        {/* Instruction / hint */}
        {voiceState !== 'error' && voiceState !== 'connecting' && (
          <p className="text-[11px] text-slate-400 text-center max-w-[220px]">
            Half-duplex mode — AI responds after each pause
          </p>
        )}

        {voiceState !== 'error' && (
          <button
            type="button"
            onClick={handleBack}
            className="mt-2 inline-flex items-center justify-center gap-2 px-4 py-2.5 text-sm font-medium rounded-sm border border-red-200 bg-red-50 text-red-900 hover:bg-red-100 transition-colors focus:outline-none focus:ring-2 focus:ring-red-800 focus:ring-offset-2"
            aria-label="End voice conversation and disconnect"
          >
            <PhoneOff size={18} strokeWidth={2} aria-hidden />
            End conversation
          </button>
        )}

        {voiceState === 'error' && (
          <button
            type="button"
            onClick={handleBack}
            className="px-4 py-2 text-sm font-medium text-white bg-blue-900 rounded-sm hover:bg-blue-800 transition-colors"
          >
            Go back
          </button>
        )}
      </div>
    </div>
  );
}
