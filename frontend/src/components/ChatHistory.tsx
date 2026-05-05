import React, { useEffect, useRef, useState } from 'react';
import { ArrowLeft } from 'lucide-react';

import { normalizeAssistantText, renderAssistantMessage } from '../utils/messageFormatting';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

type ChatRole = 'user' | 'assistant';

interface HistoryMessage {
  id: string;
  role: ChatRole;
  content: string;
  timestamp: Date;
}

interface ConversationDetail {
  id: string;
  status: string;
  created_at: string;
  updated_at: string;
  ticket_id: string | null;
  ticket_url: string | null;
}

function formatHeaderDate(iso: string): string {
  const d = new Date(iso);
  return new Intl.DateTimeFormat('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  }).format(d);
}

function statusBadgeClass(status: string): string {
  const s = status.toLowerCase();
  if (s === 'active') {
    return 'bg-blue-100 text-blue-800 border-blue-200';
  }
  if (s === 'escalated') {
    return 'bg-amber-100 text-amber-900 border-amber-200';
  }
  if (s === 'resolved') {
    return 'bg-emerald-100 text-emerald-800 border-emerald-200';
  }
  return 'bg-slate-100 text-slate-700 border-slate-200';
}

interface ChatHistoryProps {
  conversationId: number;
  onBack: () => void;
}

export function ChatHistory({ conversationId, onBack }: ChatHistoryProps) {
  const [detail, setDetail] = useState<ConversationDetail | null>(null);
  const [messages, setMessages] = useState<HistoryMessage[]>([]);
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      setError(null);
      setDetail(null);
      setMessages([]);
      try {
        const [detailRes, msgRes] = await Promise.all([
          fetch(`${API_BASE}/conversations/${conversationId}`),
          fetch(`${API_BASE}/conversations/${conversationId}/messages`),
        ]);
        if (!detailRes.ok) {
          throw new Error('Could not load conversation');
        }
        if (!msgRes.ok) {
          throw new Error('Could not load messages');
        }
        const d: ConversationDetail = await detailRes.json();
        const raw: { id: string; role: string; content: string; created_at: string }[] =
          await msgRes.json();
        if (cancelled) {
          return;
        }
        setDetail(d);
        setMessages(
          raw.map((m) => ({
            id: m.id,
            role: m.role === 'user' ? 'user' : 'assistant',
            content: m.content,
            timestamp: new Date(m.created_at),
          })),
        );
      } catch {
        if (!cancelled) {
          setError('Could not load chat history. Please try again.');
        }
      }
    };

    void load();
    return () => {
      cancelled = true;
    };
  }, [conversationId]);

  useEffect(() => {
    const el = scrollRef.current;
    if (el) {
      el.scrollTop = el.scrollHeight;
    }
  }, [messages]);

  return (
    <div className="flex flex-col h-full bg-slate-50 animate-in fade-in slide-in-from-bottom-4 duration-300">
      <header className="bg-white border-b border-slate-200 p-4 flex flex-col gap-2 shrink-0">
        <div className="flex items-center gap-3">
          <button
            onClick={onBack}
            className="p-1.5 text-slate-500 hover:text-slate-900 hover:bg-slate-100 rounded-sm transition-colors focus:outline-none focus:ring-2 focus:ring-blue-900"
            aria-label="Back to selection"
            type="button"
          >
            <ArrowLeft size={20} strokeWidth={2.5} />
          </button>
          <div className="flex-1 min-w-0">
            <h2 className="font-semibold text-slate-900 tracking-tight">Chat History</h2>
            {detail ? (
              <p className="text-xs text-slate-500 mt-0.5 truncate">
                {formatHeaderDate(detail.created_at)}
                {detail.ticket_id ? (
                  <span className="text-slate-600">
                    {' '}
                    · Ticket{' '}
                    {detail.ticket_url ? (
                      <a
                        href={detail.ticket_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-blue-900 underline hover:text-blue-800"
                      >
                        {detail.ticket_id}
                      </a>
                    ) : (
                      detail.ticket_id
                    )}
                  </span>
                ) : null}
              </p>
            ) : null}
          </div>
          {detail ? (
            <span
              className={`text-[10px] font-semibold uppercase tracking-wide px-2 py-1 rounded-sm border shrink-0 ${statusBadgeClass(detail.status)}`}
            >
              {detail.status}
            </span>
          ) : null}
        </div>
      </header>

      <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-6">
        {error ? (
          <p className="text-sm text-red-700">{error}</p>
        ) : null}
        {!error && detail === null && messages.length === 0 ? (
          <div className="flex justify-start">
            <div className="bg-white border border-slate-200 text-slate-500 text-sm p-3.5 rounded-md rounded-tl-none max-w-[85%] shadow-sm">
              Loading…
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
                  {renderAssistantMessage(normalizeAssistantText(msg.content))}
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
