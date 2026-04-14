import React, { useCallback, useEffect, useRef, useState } from 'react';
import { ArrowLeft, Loader2, Send } from 'lucide-react';

import { normalizeAssistantText, renderAssistantMessage } from '../utils/messageFormatting';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

/** Hide raw ticket block in the UI while SSE chunks are still arriving. */
function stripCreateTicketBlock(text: string): string {
  const idx = text.toLowerCase().indexOf('[create_ticket');
  if (idx === -1) {
    return text;
  }
  return text.slice(0, idx).replace(/\s+$/, '');
}

/** Split server final message into body + ticket confirmation (matches backend wording). */
function splitTicketConfirmation(message: string): { base: string; footer: string } {
  const marker = '\n\nYour support ticket has been created.';
  const idx = message.indexOf(marker);
  if (idx === -1) {
    return { base: message, footer: '' };
  }
  return { base: message.slice(0, idx), footer: message.slice(idx) };
}

const STREAM_DRAIN_MS = 17;

type ChatRole = 'user' | 'assistant';
type ConfidenceTier = 'high' | 'low' | 'none';

interface ChatMessage {
  id: string;
  role: ChatRole;
  content: string;
  timestamp: Date;
  confidence_tier?: ConfidenceTier;
}

interface ChatSseDone {
  type: 'done';
  confidence_tier: ConfidenceTier;
  conversation_id: string;
  message: string;
  sources: string[];
  ticket: { jira_ticket_id: string; jira_ticket_url: string } | null;
}

async function readChatSse(
  response: Response,
  opts: {
    onSources?: (sources: string[]) => void;
    onChunk: (text: string) => void;
    onDone: (d: ChatSseDone) => void;
    onError: (detail: string) => void;
    onProgress?: () => void;
  },
): Promise<void> {
  const reader = response.body?.getReader();
  if (!reader) {
    opts.onError('No response body');
    return;
  }
  const decoder = new TextDecoder();
  let buffer = '';
  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });
    let sep: number;
    while ((sep = buffer.indexOf('\n\n')) !== -1) {
      const block = buffer.slice(0, sep).trim();
      buffer = buffer.slice(sep + 2);
      if (!block.startsWith('data: ')) {
        continue;
      }
      let ev: unknown;
      try {
        ev = JSON.parse(block.slice(6));
      } catch {
        continue;
      }
      if (!ev || typeof ev !== 'object' || !('type' in ev)) {
        continue;
      }
      const t = (ev as { type: string }).type;
      if (t === 'sources' && 'sources' in ev) {
        opts.onSources?.((ev as { sources: string[] }).sources);
      } else if (t === 'chunk' && 'content' in ev) {
        opts.onChunk((ev as { content: string }).content);
        opts.onProgress?.();
      } else if (t === 'done') {
        opts.onDone(ev as ChatSseDone);
      } else if (t === 'error' && 'detail' in ev) {
        opts.onError((ev as { detail: string }).detail);
      }
    }
  }
}

interface TypewriterTextProps {
  fullText: string;
  speed?: number;
  onComplete?: () => void;
  onProgress?: () => void;
}

function TypewriterText({ fullText, speed = 15, onComplete, onProgress }: TypewriterTextProps) {
  const [displayedText, setDisplayedText] = useState('');
  const onCompleteRef = useRef(onComplete);
  const onProgressRef = useRef(onProgress);
  onCompleteRef.current = onComplete;
  onProgressRef.current = onProgress;

  useEffect(() => {
    setDisplayedText('');
    if (!fullText.length) {
      queueMicrotask(() => onCompleteRef.current?.());
      return;
    }

    const start = performance.now();
    let rafId = 0;
    let intervalId: number | undefined;
    let done = false;
    let lastProgressAt = 0;
    const PROGRESS_MIN_MS = 50;

    const tick = () => {
      if (done) return;
      const elapsed = performance.now() - start;
      const n = Math.min(fullText.length, Math.floor(elapsed / speed));
      setDisplayedText(fullText.slice(0, n));

      const now = performance.now();
      const finished = n >= fullText.length;
      if (finished || now - lastProgressAt >= PROGRESS_MIN_MS) {
        lastProgressAt = now;
        onProgressRef.current?.();
      }

      if (finished) {
        done = true;
        if (intervalId !== undefined) {
          clearInterval(intervalId);
          intervalId = undefined;
        }
        onCompleteRef.current?.();
      }
    };

    const rafLoop = () => {
      tick();
      if (!done) {
        rafId = requestAnimationFrame(rafLoop);
      }
    };

    const startBackgroundPump = () => {
      if (intervalId !== undefined) return;
      intervalId = window.setInterval(tick, 120);
    };

    const stopBackgroundPump = () => {
      if (intervalId !== undefined) {
        clearInterval(intervalId);
        intervalId = undefined;
      }
    };

    const syncVisibility = () => {
      if (done) return;
      if (document.hidden) {
        cancelAnimationFrame(rafId);
        startBackgroundPump();
      } else {
        stopBackgroundPump();
        tick();
        if (!done) {
          rafId = requestAnimationFrame(rafLoop);
        }
      }
    };

    tick();
    if (!done) {
      if (document.hidden) {
        startBackgroundPump();
      } else {
        rafId = requestAnimationFrame(rafLoop);
      }
    }
    document.addEventListener('visibilitychange', syncVisibility);

    return () => {
      done = true;
      cancelAnimationFrame(rafId);
      stopBackgroundPump();
      document.removeEventListener('visibilitychange', syncVisibility);
    };
  }, [fullText, speed]);

  return <>{renderAssistantMessage(displayedText)}</>;
}

interface ChatInterfaceProps {
  onBack: () => void;
}

export function ChatInterface({ onBack }: ChatInterfaceProps) {
  const [inputValue, setInputValue] = useState('');
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [conversationReady, setConversationReady] = useState(false);
  const [animatingMessageId, setAnimatingMessageId] = useState<string | null>(null);
  const [streamingAssistantId, setStreamingAssistantId] = useState<string | null>(null);
  const [waitingForFirstToken, setWaitingForFirstToken] = useState(false);
  const streamQueueRef = useRef<string[]>([]);
  const streamDrainIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const pendingDoneRef = useRef<ChatSseDone | null>(null);
  const footerDrainRef = useRef(false);
  const streamStateRef = useRef<{ assistantId: string | null; firstChunkPending: boolean }>({
    assistantId: null,
    firstChunkPending: true,
  });
  const processEmptyQueueRef = useRef<() => void>(() => {});
  const drainTickRef = useRef<() => void>(() => {});
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const stickToBottomRef = useRef(true);

  const SCROLL_NEAR_BOTTOM_PX = 80;

  const updateStickToBottom = useCallback(() => {
    const el = scrollRef.current;
    if (!el) {
      return;
    }
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    stickToBottomRef.current = distanceFromBottom < SCROLL_NEAR_BOTTOM_PX;
  }, []);

  const scrollToBottomIfPinned = useCallback(() => {
    if (!stickToBottomRef.current) {
      return;
    }
    const el = scrollRef.current;
    if (el) {
      el.scrollTop = el.scrollHeight;
    }
  }, []);

  const forceScrollToBottom = useCallback(() => {
    stickToBottomRef.current = true;
    const el = scrollRef.current;
    if (el) {
      el.scrollTop = el.scrollHeight;
    }
  }, []);

  const stopStreamDrain = useCallback(() => {
    if (streamDrainIntervalRef.current) {
      clearInterval(streamDrainIntervalRef.current);
      streamDrainIntervalRef.current = null;
    }
  }, []);

  const finalizeStreamComplete = useCallback(() => {
    stopStreamDrain();
    streamQueueRef.current = [];
    streamStateRef.current = { assistantId: null, firstChunkPending: true };
    pendingDoneRef.current = null;
    footerDrainRef.current = false;
    setWaitingForFirstToken(false);
    setStreamingAssistantId(null);
    inputRef.current?.focus();
  }, [stopStreamDrain]);

  const ensureStreamDrain = useCallback(() => {
    if (streamDrainIntervalRef.current !== null) {
      return;
    }
    streamDrainIntervalRef.current = setInterval(() => drainTickRef.current(), STREAM_DRAIN_MS);
  }, []);

  processEmptyQueueRef.current = () => {
    const id = streamStateRef.current.assistantId;
    if (!id) {
      return;
    }
    if (streamQueueRef.current.length > 0) {
      return;
    }

    if (pendingDoneRef.current) {
      const d = pendingDoneRef.current;
      pendingDoneRef.current = null;
      if (d.ticket) {
        const { base, footer } = splitTicketConfirmation(d.message);
        if (footer.length > 0) {
          setMessages((prev) => {
            const hasRow = prev.some((m) => m.id === id);
            if (!hasRow) {
              return [
                ...prev,
                {
                  id,
                  role: 'assistant',
                  content: base,
                  timestamp: new Date(),
                  confidence_tier: d.confidence_tier,
                },
              ];
            }
            return prev.map((m) =>
              m.id === id
                ? { ...m, content: base, confidence_tier: d.confidence_tier }
                : m,
            );
          });
          footerDrainRef.current = true;
          for (const char of Array.from(footer)) {
            streamQueueRef.current.push(char);
          }
          ensureStreamDrain();
          return;
        }
      }
      setMessages((prev) => {
        const hasRow = prev.some((m) => m.id === id);
        if (!hasRow) {
          return [
            ...prev,
            {
              id,
              role: 'assistant',
              content: d.message,
              timestamp: new Date(),
              confidence_tier: d.confidence_tier,
            },
          ];
        }
        return prev.map((m) =>
          m.id === id
            ? { ...m, content: d.message, confidence_tier: d.confidence_tier }
            : m,
        );
      });
      finalizeStreamComplete();
      return;
    }

    if (footerDrainRef.current) {
      footerDrainRef.current = false;
      finalizeStreamComplete();
      return;
    }

    stopStreamDrain();
  };

  drainTickRef.current = () => {
    const id = streamStateRef.current.assistantId;
    if (!id) {
      return;
    }
    const q = streamQueueRef.current;
    if (q.length > 0) {
      const piece = q.shift()!;
      setMessages((prev) =>
        prev.map((m) => (m.id === id ? { ...m, content: m.content + piece } : m)),
      );
      queueMicrotask(() => scrollToBottomIfPinned());
      if (streamQueueRef.current.length === 0) {
        processEmptyQueueRef.current();
      }
      return;
    }

    processEmptyQueueRef.current();
  };

  const enqueueStreamChunk = useCallback(
    (text: string) => {
      const st = streamStateRef.current;
      if (st.firstChunkPending && st.assistantId) {
        st.firstChunkPending = false;
        setWaitingForFirstToken(false);
        setStreamingAssistantId(st.assistantId);
        setMessages((prev) => {
          if (prev.some((m) => m.id === st.assistantId)) {
            return prev;
          }
          return [
            ...prev,
            {
              id: st.assistantId!,
              role: 'assistant',
              content: '',
              timestamp: new Date(),
              confidence_tier: 'none',
            },
          ];
        });
      }
      for (const char of Array.from(text)) {
        streamQueueRef.current.push(char);
      }
      ensureStreamDrain();
    },
    [ensureStreamDrain],
  );

  useEffect(() => {
    return () => {
      if (streamDrainIntervalRef.current) {
        clearInterval(streamDrainIntervalRef.current);
      }
    };
  }, []);

  useEffect(() => {
    let cancelled = false;

    const bootstrap = async () => {
      try {
        const convRes = await fetch(`${API_BASE}/conversations`, { method: 'POST' });
        if (!convRes.ok) {
          throw new Error('Failed to create conversation');
        }
        const convData: { id: string } = await convRes.json();
        if (cancelled) {
          return;
        }
        setConversationId(convData.id);
        setIsLoading(true);

        const greetingId = crypto.randomUUID();
        stopStreamDrain();
        streamQueueRef.current = [];
        pendingDoneRef.current = null;
        footerDrainRef.current = false;
        streamStateRef.current = { assistantId: greetingId, firstChunkPending: true };
        setWaitingForFirstToken(true);

        const chatRes = await fetch(`${API_BASE}/chat`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Accept: 'text/event-stream',
          },
          body: JSON.stringify({
            message: 'hello',
            conversation_id: convData.id,
          }),
        });

        if (!chatRes.ok) {
          throw new Error('Failed to load greeting');
        }

        if (cancelled) {
          return;
        }

        await readChatSse(chatRes, {
          onChunk: (text) => {
            enqueueStreamChunk(text);
          },
          onProgress: scrollToBottomIfPinned,
          onDone: (d) => {
            pendingDoneRef.current = d;
            if (streamQueueRef.current.length === 0) {
              ensureStreamDrain();
            }
          },
          onError: () => {
            stopStreamDrain();
            streamQueueRef.current = [];
            pendingDoneRef.current = null;
            footerDrainRef.current = false;
            streamStateRef.current = { assistantId: null, firstChunkPending: true };
            setWaitingForFirstToken(false);
            setStreamingAssistantId(null);
            setMessages((prev) => {
              const errText =
                'Could not load the greeting. Please check your connection and try again.';
              const has = prev.some((m) => m.id === greetingId);
              if (has) {
                return prev.map((m) =>
                  m.id === greetingId ? { ...m, content: errText } : m,
                );
              }
              return [
                ...prev,
                {
                  id: greetingId,
                  role: 'assistant',
                  content: errText,
                  timestamp: new Date(),
                },
              ];
            });
          },
        });
      } catch {
        if (!cancelled) {
          stopStreamDrain();
          streamQueueRef.current = [];
          pendingDoneRef.current = null;
          footerDrainRef.current = false;
          streamStateRef.current = { assistantId: null, firstChunkPending: true };
          setWaitingForFirstToken(false);
          setConversationId(null);
          setStreamingAssistantId(null);
          const errId = crypto.randomUUID();
          setMessages([
            {
              id: errId,
              role: 'assistant',
              content:
                'Could not start a conversation. Please check your connection and try again.',
              timestamp: new Date(),
            },
          ]);
          setAnimatingMessageId(errId);
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false);
          setConversationReady(true);
        }
      }
    };

    void bootstrap();
    return () => {
      cancelled = true;
    };
    // Mount-only: conversation + greeting stream (handlers from first render are sufficient).
    // eslint-disable-next-line react-hooks/exhaustive-deps -- run once
  }, []);

  useEffect(() => {
    scrollToBottomIfPinned();
  }, [messages, isLoading, waitingForFirstToken, scrollToBottomIfPinned]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = inputValue.trim();
    if (!trimmed || !conversationId || isLoading || animatingMessageId !== null) {
      return;
    }

    const userMessage: ChatMessage = {
      id: crypto.randomUUID(),
      role: 'user',
      content: trimmed,
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInputValue('');
    stickToBottomRef.current = true;
    queueMicrotask(() => {
      forceScrollToBottom();
    });
    setIsLoading(true);

    const assistantId = crypto.randomUUID();
    stopStreamDrain();
    streamQueueRef.current = [];
    pendingDoneRef.current = null;
    footerDrainRef.current = false;
    streamStateRef.current = { assistantId, firstChunkPending: true };
    setWaitingForFirstToken(true);

    try {
      const res = await fetch(`${API_BASE}/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Accept: 'text/event-stream',
        },
        body: JSON.stringify({
          message: trimmed,
          conversation_id: conversationId,
        }),
      });

      if (!res.ok) {
        throw new Error('Chat request failed');
      }

      await readChatSse(res, {
        onChunk: (text) => {
          enqueueStreamChunk(text);
        },
        onProgress: scrollToBottomIfPinned,
        onDone: (d) => {
          pendingDoneRef.current = d;
          if (streamQueueRef.current.length === 0) {
            ensureStreamDrain();
          }
        },
        onError: () => {
          stopStreamDrain();
          streamQueueRef.current = [];
          pendingDoneRef.current = null;
          footerDrainRef.current = false;
          streamStateRef.current = { assistantId: null, firstChunkPending: true };
          setWaitingForFirstToken(false);
          setStreamingAssistantId(null);
          setMessages((prev) => {
            const errText = 'Connection error. Please try again.';
            const has = prev.some((m) => m.id === assistantId);
            if (has) {
              return prev.map((m) =>
                m.id === assistantId ? { ...m, content: errText } : m,
              );
            }
            return [
              ...prev,
              {
                id: assistantId,
                role: 'assistant',
                content: errText,
                timestamp: new Date(),
              },
            ];
          });
          inputRef.current?.focus();
        },
      });
    } catch {
      stopStreamDrain();
      streamQueueRef.current = [];
      pendingDoneRef.current = null;
      footerDrainRef.current = false;
      streamStateRef.current = { assistantId: null, firstChunkPending: true };
      setWaitingForFirstToken(false);
      setStreamingAssistantId(null);
      setMessages((prev) => {
        const errText = 'Connection error. Please try again.';
        const has = prev.some((m) => m.id === assistantId);
        if (has) {
          return prev.map((m) =>
            m.id === assistantId ? { ...m, content: errText } : m,
          );
        }
        return [
          ...prev,
          {
            id: assistantId,
            role: 'assistant',
            content: errText,
            timestamp: new Date(),
          },
        ];
      });
      inputRef.current?.focus();
    } finally {
      setIsLoading(false);
    }
  };

  const isTyping = animatingMessageId !== null;
  const isStreaming = streamingAssistantId !== null;

  const canSend =
    Boolean(inputValue.trim()) &&
    Boolean(conversationId) &&
    !isLoading &&
    conversationReady &&
    !isTyping &&
    !isStreaming;

  return (
    <div className="flex flex-col h-full bg-slate-50 animate-in fade-in slide-in-from-bottom-4 duration-300">
      {/* Header */}
      <header className="bg-white border-b border-slate-200 p-4 flex items-center gap-3 shrink-0">
        <button
          onClick={onBack}
          className="p-1.5 text-slate-500 hover:text-slate-900 hover:bg-slate-100 rounded-sm transition-colors focus:outline-none focus:ring-2 focus:ring-blue-900"
          aria-label="Go back to selection screen"
        >
          <ArrowLeft size={20} strokeWidth={2.5} />
        </button>
        <div className="flex items-center gap-2 flex-1">
          <h2 className="font-semibold text-slate-900 tracking-tight">Infleet AI Assistant</h2>
          <span className="relative flex h-2.5 w-2.5">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
            <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-green-500"></span>
          </span>
        </div>
      </header>

      {/* Chat History Area */}
      <div
        ref={scrollRef}
        onScroll={updateStickToBottom}
        className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-6"
      >
        {!conversationReady && !conversationId ? (
          <div className="flex justify-start">
            <div className="bg-white border border-slate-200 text-slate-600 text-sm p-3.5 rounded-md rounded-tl-none max-w-[85%] shadow-sm leading-relaxed">
              Connecting…
            </div>
          </div>
        ) : null}
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={msg.role === 'user' ? 'flex justify-end' : 'flex justify-start'}
          >
            {msg.role === 'user' ? (
              <div className="bg-blue-900 text-white text-sm p-3.5 rounded-md rounded-tr-none max-w-[85%] shadow-sm leading-relaxed">
                {msg.content}
              </div>
            ) : (
              <div className="max-w-[85%]">
                <div className="bg-white border border-slate-200 text-slate-900 text-sm p-3.5 rounded-md rounded-tl-none shadow-sm leading-relaxed">
                  {msg.role === 'assistant' &&
                  msg.id === animatingMessageId &&
                  msg.id !== streamingAssistantId ? (
                    <TypewriterText
                      fullText={normalizeAssistantText(msg.content)}
                      speed={15}
                      onProgress={scrollToBottomIfPinned}
                      onComplete={() => {
                        setAnimatingMessageId(null);
                        inputRef.current?.focus();
                      }}
                    />
                  ) : (
                    <>
                      {renderAssistantMessage(
                        normalizeAssistantText(
                          msg.role === 'assistant' && msg.id === streamingAssistantId
                            ? stripCreateTicketBlock(msg.content)
                            : msg.content,
                        ),
                      )}
                      {msg.role === 'assistant' &&
                      msg.id === streamingAssistantId &&
                      msg.content.toLowerCase().includes('[create_ticket') ? (
                        <div
                          className="mt-3 pt-3 border-t border-slate-100 flex items-center gap-2.5 text-slate-600 text-sm min-h-[2.25rem]"
                          role="status"
                          aria-live="polite"
                        >
                          <Loader2
                            className="w-4 h-4 shrink-0 animate-spin text-slate-500"
                            aria-hidden
                          />
                          <span className="leading-snug">Creating support ticket…</span>
                        </div>
                      ) : null}
                    </>
                  )}
                </div>
              </div>
            )}
          </div>
        ))}
        {isLoading && waitingForFirstToken ? (
          <div className="flex justify-start">
            <div className="bg-white border border-slate-200 text-slate-500 text-sm p-3.5 rounded-md rounded-tl-none max-w-[85%] shadow-sm leading-relaxed flex items-center gap-1.5">
              <span className="inline-flex gap-1">
                <span className="w-1.5 h-1.5 bg-slate-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                <span className="w-1.5 h-1.5 bg-slate-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                <span className="w-1.5 h-1.5 bg-slate-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
              </span>
            </div>
          </div>
        ) : null}
      </div>

      {/* Input Area */}
      <div className="p-4 bg-white border-t border-slate-200 shrink-0">
        <form onSubmit={handleSubmit} className="flex gap-2 items-end">
          <textarea
            ref={inputRef}
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey && !e.ctrlKey && !e.metaKey) {
                e.preventDefault();
                if (canSend) {
                  e.currentTarget.form?.requestSubmit();
                }
              }
            }}
            rows={1}
            placeholder="Type your message..."
            disabled={!conversationId || !conversationReady || isLoading || isTyping || isStreaming}
            className="flex-1 min-h-[44px] max-h-40 resize-none border border-slate-300 rounded-sm px-3.5 py-2.5 text-sm focus:outline-none focus:border-blue-900 focus:ring-1 focus:ring-blue-900 placeholder:text-slate-400 transition-shadow disabled:bg-slate-100 disabled:text-slate-500"
          />
          <button
            type="submit"
            disabled={!canSend}
            className="bg-blue-900 hover:bg-blue-800 disabled:bg-slate-300 disabled:text-slate-500 text-white px-4 py-2.5 rounded-sm transition-colors focus:outline-none focus:ring-2 focus:ring-blue-900 focus:ring-offset-2 flex items-center justify-center"
            aria-label="Send message"
          >
            <Send
              size={18}
              strokeWidth={2}
              className={canSend ? 'translate-x-0.5' : ''}
            />
          </button>
        </form>
      </div>
    </div>
  );
}
