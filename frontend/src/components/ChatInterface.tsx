import React, { useCallback, useEffect, useRef, useState } from 'react';
import { ArrowLeft, Send } from 'lucide-react';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

type ChatRole = 'user' | 'assistant';
type ConfidenceTier = 'high' | 'low' | 'none';

interface ChatMessage {
  id: string;
  role: ChatRole;
  content: string;
  timestamp: Date;
  confidence_tier?: ConfidenceTier;
}

interface ChatApiResponse {
  message: string;
  conversation_id: string;
  confidence_tier: ConfidenceTier;
  sources: string[];
}

/** Strip common inline markdown; keep visible text only. */
function stripInlineMarkdown(s: string): string {
  let t = s;
  t = t.replace(/\[([^\]]+)\]\([^)]+\)/g, '$1');
  t = t.replace(/\*\*(.+?)\*\*/g, '$1');
  t = t.replace(/__(.+?)__/g, '$1');
  t = t.replace(/`([^`]+)`/g, '$1');
  t = t.replace(/\*(.+?)\*/g, '$1');
  t = t.replace(/_(.+?)_/g, '$1');
  return t;
}

/** Remove markdown markers and normalize list lines to leading "• " for display. */
function normalizeAssistantText(raw: string): string {
  const lines = raw.split(/\r?\n/);
  const out: string[] = [];
  for (const line of lines) {
    const trimmed = line.trim();
    if (trimmed === '') {
      out.push('');
      continue;
    }
    if (/^-{3,}$/.test(trimmed)) {
      out.push('');
      continue;
    }
    const heading = trimmed.match(/^#{1,6}\s+(.+)$/);
    if (heading) {
      out.push(stripInlineMarkdown(heading[1]));
      continue;
    }
    const bullet = trimmed.match(/^[-*+]\s+(.+)$/);
    if (bullet) {
      out.push('• ' + stripInlineMarkdown(bullet[1]));
      continue;
    }
    const ordered = trimmed.match(/^\d+\.\s+(.+)$/);
    if (ordered) {
      out.push('• ' + stripInlineMarkdown(ordered[1]));
      continue;
    }
    out.push(stripInlineMarkdown(trimmed));
  }
  return out.join('\n');
}

/** Drop blank lines between consecutive bullet rows so lists stay visually tight. */
function collapseBlankLinesBetweenBullets(lines: string[]): string[] {
  const out: string[] = [];
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (line.trim() === '') {
      const prev = out[out.length - 1];
      const nextNonEmpty = lines.slice(i + 1).find((l) => l.trim() !== '');
      if (prev?.trimStart().startsWith('• ') && nextNonEmpty?.trimStart().startsWith('• ')) {
        continue;
      }
    }
    out.push(line);
  }
  return out;
}

function renderAssistantMessage(text: string): React.ReactNode {
  if (!text) {
    return null;
  }
  const lines = collapseBlankLinesBetweenBullets(text.split('\n'));
  return (
    <div className="flex flex-col gap-1">
      {lines.map((line, idx) => {
        if (line.trim() === '') {
          return <div key={idx} className="h-1 shrink-0" aria-hidden />;
        }
        if (line.startsWith('• ')) {
          return (
            <div key={idx} className="flex gap-2 items-start py-0 leading-snug">
              <span className="shrink-0 text-slate-600 select-none pt-0.5" aria-hidden>
                •
              </span>
              <span className="flex-1 min-w-0">{line.slice(2)}</span>
            </div>
          );
        }
        return (
          <p key={idx} className="leading-relaxed m-0 first:mt-0">
            {line}
          </p>
        );
      })}
    </div>
  );
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

        const chatRes = await fetch(`${API_BASE}/chat`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            message: 'hello',
            conversation_id: convData.id,
          }),
        });

        if (!chatRes.ok) {
          throw new Error('Failed to load greeting');
        }

        const data: ChatApiResponse = await chatRes.json();
        if (cancelled) {
          return;
        }

        const greetingId = crypto.randomUUID();
        setMessages([
          {
            id: greetingId,
            role: 'assistant',
            content: data.message,
            timestamp: new Date(),
            confidence_tier: data.confidence_tier,
          },
        ]);
        setAnimatingMessageId(greetingId);
      } catch {
        if (!cancelled) {
          setConversationId(null);
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
  }, []);

  useEffect(() => {
    scrollToBottomIfPinned();
  }, [messages, isLoading, scrollToBottomIfPinned]);

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

    try {
      const res = await fetch(`${API_BASE}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: trimmed,
          conversation_id: conversationId,
        }),
      });

      if (!res.ok) {
        throw new Error('Chat request failed');
      }

      const data: ChatApiResponse = await res.json();
      const assistantId = crypto.randomUUID();
      const assistantMessage: ChatMessage = {
        id: assistantId,
        role: 'assistant',
        content: data.message,
        timestamp: new Date(),
        confidence_tier: data.confidence_tier,
      };
      setMessages((prev) => [...prev, assistantMessage]);
      setAnimatingMessageId(assistantId);
    } catch {
      const errId = crypto.randomUUID();
      const errMessage: ChatMessage = {
        id: errId,
        role: 'assistant',
        content: 'Connection error. Please try again.',
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, errMessage]);
      setAnimatingMessageId(errId);
    } finally {
      setIsLoading(false);
    }
  };

  const isTyping = animatingMessageId !== null;

  const canSend =
    Boolean(inputValue.trim()) &&
    Boolean(conversationId) &&
    !isLoading &&
    conversationReady &&
    !isTyping;

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
                {msg.confidence_tier === 'low' ? (
                  <p className="text-xs italic text-amber-800 mb-1">
                    ⚠ I&apos;m not fully certain about this
                  </p>
                ) : null}
                <div className="bg-white border border-slate-200 text-slate-900 text-sm p-3.5 rounded-md rounded-tl-none shadow-sm leading-relaxed">
                  {msg.role === 'assistant' && msg.id === animatingMessageId ? (
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
                    renderAssistantMessage(normalizeAssistantText(msg.content))
                  )}
                </div>
              </div>
            )}
          </div>
        ))}
        {isLoading ? (
          <div className="flex justify-start">
            <div className="bg-white border border-slate-200 text-slate-500 text-sm p-3.5 rounded-md rounded-tl-none max-w-[85%] shadow-sm leading-relaxed flex items-center gap-1.5">
              <span className="inline-flex gap-1">
                <span className="w-1.5 h-1.5 bg-slate-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                <span className="w-1.5 h-1.5 bg-slate-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                <span className="w-1.5 h-1.5 bg-slate-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
              </span>
              <span className="italic ml-1">Thinking...</span>
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
            disabled={!conversationId || !conversationReady || isLoading || isTyping}
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
