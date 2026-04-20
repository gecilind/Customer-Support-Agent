import React, { useCallback, useEffect, useRef, useState } from 'react';
import { ArrowLeft, Mic, Loader2, PhoneOff, Volume2 } from 'lucide-react';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type VoiceMode = 'listening' | 'processing' | 'speaking';
type VoiceState = 'connecting' | VoiceMode | 'error';

interface TranscriptEntry {
  role: 'user' | 'assistant';
  text: string;
  ticketUrl?: string;
}

interface Props {
  onBack: () => void;
}

function formatPlaybackTs(): string {
  const d = new Date();
  const pad = (n: number) => n.toString().padStart(2, '0');
  const ms = d.getMilliseconds().toString().padStart(3, '0');
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}.${ms}`;
}

function applyWorkletMute(worklet: AudioWorkletNode | null, mode: VoiceMode | 'connecting') {
  if (!worklet) return;
  const muted = mode !== 'listening';
  worklet.port.postMessage({ type: 'set_muted', value: muted });
}

// ---------------------------------------------------------------------------
// Audio helpers
// ---------------------------------------------------------------------------

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
  const [transcripts, setTranscripts] = useState<TranscriptEntry[]>([]);

  const wsRef = useRef<WebSocket | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const workletNodeRef = useRef<AudioWorkletNode | null>(null);
  const micStreamRef = useRef<MediaStream | null>(null);
  const nextPlayTimeRef = useRef<number>(0);
  const playbackPendingRef = useRef(0);
  const ttsStreamEndedRef = useRef(false);
  const activePlaybackSourcesRef = useRef<AudioBufferSourceNode[]>([]);

  const listeningStartTsRef = useRef<string>('');
  const mutedStartTsRef = useRef<string>('');

  const trySendPlaybackDrained = useCallback(() => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    if (playbackPendingRef.current !== 0 || !ttsStreamEndedRef.current) return;
    ttsStreamEndedRef.current = false;
    ws.send(JSON.stringify({ type: 'playback_drained', ts: formatPlaybackTs() }));
  }, []);

  const playAudioChunk = useCallback(
    (bytes: ArrayBuffer) => {
      const ctx = audioCtxRef.current;
      if (!ctx) return;
      if (ctx.state === 'suspended') {
        void ctx.resume();
      }

      const float32 = pcm16BytesToFloat32(bytes);
      const audioBuf = ctx.createBuffer(1, float32.length, 24_000);
      audioBuf.getChannelData(0).set(float32);

      const source = ctx.createBufferSource();
      source.buffer = audioBuf;
      source.playbackRate.value = 1.1; // was 1.15
      source.connect(ctx.destination);

      const now = ctx.currentTime;
      const startAt = Math.max(now, nextPlayTimeRef.current);
      source.start(startAt);
      nextPlayTimeRef.current = startAt + audioBuf.duration / source.playbackRate.value;

      playbackPendingRef.current += 1;
      activePlaybackSourcesRef.current.push(source);
      source.onended = () => {
        activePlaybackSourcesRef.current = activePlaybackSourcesRef.current.filter((n) => n !== source);
        playbackPendingRef.current -= 1;
        if (playbackPendingRef.current <= 0) {
          playbackPendingRef.current = 0;
        }
        trySendPlaybackDrained();
      };
    },
    [trySendPlaybackDrained],
  );

  const teardown = useCallback(() => {
    try {
      wsRef.current?.close();
    } catch {
      /* ignore */
    }
    try {
      workletNodeRef.current?.disconnect();
    } catch {
      /* ignore */
    }
    micStreamRef.current?.getTracks().forEach((t) => t.stop());
    audioCtxRef.current?.suspend().catch(() => {
      /* ignore */
    });
  }, []);

  const handleBack = useCallback(() => {
    teardown();
    onBack();
  }, [teardown, onBack]);

  useEffect(() => {
    let cancelled = false;

    const setup = async () => {
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
      if (cancelled) {
        stream.getTracks().forEach((t) => t.stop());
        return;
      }
      micStreamRef.current = stream;

      const ctx = new AudioContext();
      audioCtxRef.current = ctx;
      try {
        await ctx.resume();
      } catch {
        /* ignore */
      }

      try {
        const workletUrl = new URL('../audio/pcm-worklet.ts', import.meta.url);
        await ctx.audioWorklet.addModule(workletUrl);
      } catch {
        const code = `
          class PCMProcessor extends AudioWorkletProcessor {
            constructor() {
              super();
              this.muted = true;
              this.port.onmessage = (e) => {
                if (e.data?.type === 'set_muted') this.muted = Boolean(e.data.value);
              };
            }
            process(inputs) {
              if (this.muted) return true;
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

      if (cancelled) {
        stream.getTracks().forEach((t) => t.stop());
        return;
      }

      const source = ctx.createMediaStreamSource(stream);
      const workletNode = new AudioWorkletNode(ctx, 'pcm-processor');
      workletNodeRef.current = workletNode;
      source.connect(workletNode);
      applyWorkletMute(workletNode, 'connecting');

      const base = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/+$/, '');
      const wsUrl = `${base.replace(/^http/, 'ws')}/voice-relay`;
      const ws = new WebSocket(wsUrl);
      ws.binaryType = 'arraybuffer';
      wsRef.current = ws;

      ws.onopen = () => {
        nextPlayTimeRef.current = 0;
        playbackPendingRef.current = 0;
        ttsStreamEndedRef.current = false;
      };

      ws.onmessage = (evt: MessageEvent) => {
        if (typeof evt.data === 'string') {
          try {
            const msg = JSON.parse(evt.data) as {
              type: string;
              mode?: VoiceMode;
              ts?: string;
              message?: string;
              role?: 'user' | 'assistant';
              text?: string;
              url?: string;
              conversation_id?: string;
            };

            if (msg.type === 'transcript' && msg.role && msg.text) {
              if (!cancelled) {
                setTranscripts((prev) => [...prev, { role: msg.role!, text: msg.text! }]);
              }
              return;
            }

            if (msg.type === 'ticket_created' && msg.url) {
              if (!cancelled) {
                setTranscripts((prev) => {
                  const next = [...prev];
                  if (next.length && next[next.length - 1].role === 'assistant') {
                    next[next.length - 1] = {
                      ...next[next.length - 1],
                      ticketUrl: msg.url,
                    };
                  }
                  return next;
                });
              }
              return;
            }

            if (msg.type === 'flush_audio') {
              const ctxFlush = audioCtxRef.current;
              if (ctxFlush) {
                nextPlayTimeRef.current = ctxFlush.currentTime;
              }
              for (const s of activePlaybackSourcesRef.current) {
                try {
                  s.stop(0);
                } catch {
                  /* already stopped */
                }
              }
              activePlaybackSourcesRef.current = [];
              playbackPendingRef.current = 0;
              ttsStreamEndedRef.current = true;
              trySendPlaybackDrained();
              return;
            }

            if (msg.type === 'mode_start' && msg.mode && msg.ts) {
              if (cancelled) return;
              setVoiceState(msg.mode);
              if (msg.mode === 'listening') {
                listeningStartTsRef.current = msg.ts;
                applyWorkletMute(workletNodeRef.current, 'listening');
              } else if (msg.mode === 'processing') {
                mutedStartTsRef.current = msg.ts;
                applyWorkletMute(workletNodeRef.current, 'processing');
              } else if (msg.mode === 'speaking') {
                applyWorkletMute(workletNodeRef.current, 'speaking');
              }
              return;
            }

            if (msg.type === 'mode_end' && msg.mode && msg.ts) {
              if (msg.mode === 'listening') {
                console.info(
                  `Mic: UNMUTED   Start: ${listeningStartTsRef.current}   End: ${msg.ts}`,
                );
              } else if (msg.mode === 'speaking') {
                console.info(`Mic: MUTED     Start: ${mutedStartTsRef.current}   End: ${msg.ts}`);
              }
              return;
            }

            if (msg.type === 'tts_stream_ended') {
              ttsStreamEndedRef.current = true;
              trySendPlaybackDrained();
              return;
            }

            if (msg.type === 'error') {
              if (!cancelled) {
                setErrorMsg(msg.message ?? 'An error occurred.');
                setVoiceState('error');
              }
            }
          } catch {
            /* non-JSON */
          }
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

      workletNode.port.onmessage = (e: MessageEvent<ArrayBuffer>) => {
        if (ws.readyState !== WebSocket.OPEN) return;
        ws.send(e.data);
      };
    };

    void setup();

    return () => {
      cancelled = true;
      teardown();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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

  return (
    <div className="flex flex-col h-full bg-white animate-in fade-in duration-300">
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

      <div className="flex flex-col flex-1 min-h-0">
        <div className="flex flex-col flex-1 items-center justify-center gap-10 px-8 overflow-y-auto">
          <div className="flex items-center justify-center min-h-[100px]">{cfg.icon}</div>

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

          {voiceState !== 'error' && voiceState !== 'connecting' && (
            <p className="text-[11px] text-slate-400 text-center max-w-[220px]">
              Half-duplex mode — AI responds after each pause
            </p>
          )}
        </div>

        {transcripts.length > 0 && (
          <div className="w-full max-h-[200px] overflow-y-auto px-4 py-3 border-t border-slate-200 space-y-2 shrink-0">
            {transcripts.map((t, i) => (
              <div
                key={i}
                className={`text-xs px-3 py-2 rounded-lg max-w-[85%] ${
                  t.role === 'user'
                    ? 'ml-auto bg-blue-50 text-blue-900'
                    : 'mr-auto bg-slate-100 text-slate-900'
                }`}
              >
                <p>{t.text}</p>
                {t.ticketUrl && (
                  <a
                    href={t.ticketUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="block mt-1 text-[10px] font-semibold text-blue-700 underline"
                  >
                    View ticket: {t.ticketUrl.split('/').pop()}
                  </a>
                )}
              </div>
            ))}
          </div>
        )}

        {voiceState !== 'error' && (
          <button
            type="button"
            onClick={handleBack}
            className="mt-auto shrink-0 m-4 inline-flex items-center justify-center gap-2 px-4 py-2.5 text-sm font-medium rounded-sm border border-red-200 bg-red-50 text-red-900 hover:bg-red-100 transition-colors focus:outline-none focus:ring-2 focus:ring-red-800 focus:ring-offset-2 self-center"
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
