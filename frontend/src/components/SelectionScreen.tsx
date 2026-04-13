import React, { useEffect, useState } from 'react';
import { MessageSquare, Mic } from 'lucide-react';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

interface ConversationRow {
  id: string;
  status: string;
  created_at: string;
  updated_at: string;
}

function formatListDate(iso: string): string {
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

interface SelectionScreenProps {
  onSelectChat: () => void;
  onSelectHistory: (conversationId: number) => void;
  onSelectVoice: () => void;
}

export function SelectionScreen({ onSelectChat, onSelectHistory, onSelectVoice }: SelectionScreenProps) {
  const [conversations, setConversations] = useState<ConversationRow[] | null>(null);
  const [listError, setListError] = useState(false);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      try {
        const res = await fetch(`${API_BASE}/conversations`);
        if (!res.ok) {
          throw new Error('failed');
        }
        const data: ConversationRow[] = await res.json();
        if (!cancelled) {
          setConversations(data);
          setListError(false);
        }
      } catch {
        if (!cancelled) {
          setConversations([]);
          setListError(true);
        }
      }
    };

    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="flex flex-col h-full p-6 sm:p-8 bg-white animate-in fade-in duration-300 min-h-0">
      <div className="mb-6 shrink-0">
        <h1 className="text-2xl font-bold text-slate-900 mb-2 tracking-tight">
          Infleet Support
        </h1>
        <p className="text-sm text-slate-600">
          How would you like to interact with our AI Assistant?
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 shrink-0">
        <button
          onClick={onSelectChat}
          className="flex flex-col items-start p-5 border border-slate-200 rounded-md hover:border-blue-900 hover:bg-slate-50 transition-all group focus:outline-none focus:ring-2 focus:ring-blue-900 focus:ring-offset-2 text-left bg-white shadow-sm hover:shadow-md"
          aria-label="Select Chatbot"
          type="button"
        >
          <div className="p-2.5 bg-blue-50 text-blue-900 rounded-sm mb-4 group-hover:bg-blue-100 transition-colors">
            <MessageSquare size={24} strokeWidth={2} />
          </div>
          <h2 className="font-semibold text-slate-900 text-lg mb-1">Chatbot</h2>
          <p className="text-sm text-slate-500 leading-relaxed">
            Type your questions for instant answers.
          </p>
        </button>

        <button
          onClick={onSelectVoice}
          className="flex flex-col items-start p-5 border border-slate-200 rounded-md hover:border-blue-900 hover:bg-slate-50 transition-all group focus:outline-none focus:ring-2 focus:ring-blue-900 focus:ring-offset-2 text-left bg-white shadow-sm hover:shadow-md"
          aria-label="Select Voice Agent"
          type="button"
        >
          <div className="p-2.5 bg-blue-50 text-blue-900 rounded-sm mb-4 group-hover:bg-blue-100 transition-colors">
            <Mic size={24} strokeWidth={2} />
          </div>
          <h2 className="font-semibold text-slate-900 text-lg mb-1">Voice Agent</h2>
          <p className="text-sm text-slate-500 leading-relaxed">Speak directly with our AI.</p>
        </button>
      </div>

      <div className="mt-8 flex flex-col min-h-0 flex-1">
        <h3 className="text-sm font-semibold text-slate-800 mb-2 tracking-tight">Previous Chats</h3>
        <div className="max-h-[200px] overflow-y-auto rounded-md border border-slate-200 bg-slate-50/80">
          {conversations === null ? (
            <p className="text-sm text-slate-500 p-3">Loading…</p>
          ) : listError ? (
            <p className="text-sm text-slate-500 p-3">Could not load conversations.</p>
          ) : conversations.length === 0 ? (
            <p className="text-sm text-slate-500 p-3">No previous conversations</p>
          ) : (
            <ul className="divide-y divide-slate-200">
              {conversations.map((c) => (
                <li key={c.id}>
                  <button
                    type="button"
                    onClick={() => onSelectHistory(Number(c.id))}
                    className="w-full flex items-center justify-between gap-3 px-3 py-2.5 text-left text-sm hover:bg-white hover:border-transparent transition-colors focus:outline-none focus:ring-2 focus:ring-inset focus:ring-blue-900"
                  >
                    <span className="text-slate-700 truncate">{formatListDate(c.created_at)}</span>
                    <span
                      className={`text-[10px] font-semibold uppercase tracking-wide px-2 py-0.5 rounded-sm border shrink-0 ${statusBadgeClass(c.status)}`}
                    >
                      {c.status}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
