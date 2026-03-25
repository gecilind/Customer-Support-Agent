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

    let i = 0;
    const timer = window.setInterval(() => {
      i += 1;
      setDisplayedText(fullText.slice(0, i));
      onProgressRef.current?.();
      if (i >= fullText.length) {
        clearInterval(timer);
        onCompleteRef.current?.();
      }
    }, speed);

    return () => clearInterval(timer);
  }, [fullText, speed]);

  return <>{displayedText}</>;
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
  const inputRef = useRef<HTMLInputElement>(null);

  const scrollToBottom = useCallback(() => {
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
    scrollToBottom();
  }, [messages, isLoading, scrollToBottom]);

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
                      fullText={msg.content}
                      speed={15}
                      onProgress={scrollToBottom}
                      onComplete={() => {
                        setAnimatingMessageId(null);
                        inputRef.current?.focus();
                      }}
                    />
                  ) : (
                    msg.content
                  )}
                </div>
              </div>
            )}
          </div>
        ))}
        {isLoading ? (
          <div className="flex justify-start">
            <div className="bg-white border border-slate-200 text-slate-500 text-sm p-3.5 rounded-md rounded-tl-none max-w-[85%] shadow-sm leading-relaxed italic">
              Thinking...
            </div>
          </div>
        ) : null}
      </div>

      {/* Input Area */}
      <div className="p-4 bg-white border-t border-slate-200 shrink-0">
        <form onSubmit={handleSubmit} className="flex gap-2">
          <input
            ref={inputRef}
            type="text"
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            placeholder="Type your message..."
            disabled={!conversationId || !conversationReady || isLoading || isTyping}
            className="flex-1 border border-slate-300 rounded-sm px-3.5 py-2.5 text-sm focus:outline-none focus:border-blue-900 focus:ring-1 focus:ring-blue-900 placeholder:text-slate-400 transition-shadow disabled:bg-slate-100 disabled:text-slate-500"
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
