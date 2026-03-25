import React, { useState } from 'react';
import { ArrowLeft, Send } from 'lucide-react';
interface ChatInterfaceProps {
  onBack: () => void;
}
export function ChatInterface({ onBack }: ChatInterfaceProps) {
  const [inputValue, setInputValue] = useState('');
  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (inputValue.trim()) {
      // In a real app, this would add the message to the chat history
      setInputValue('');
    }
  };
  return (
    <div className="flex flex-col h-full bg-slate-50 animate-in fade-in slide-in-from-bottom-4 duration-300">
      {/* Header */}
      <header className="bg-white border-b border-slate-200 p-4 flex items-center gap-3 shrink-0">
        <button
          onClick={onBack}
          className="p-1.5 text-slate-500 hover:text-slate-900 hover:bg-slate-100 rounded-sm transition-colors focus:outline-none focus:ring-2 focus:ring-blue-900"
          aria-label="Go back to selection screen">
          
          <ArrowLeft size={20} strokeWidth={2.5} />
        </button>
        <div className="flex items-center gap-2 flex-1">
          <h2 className="font-semibold text-slate-900 tracking-tight">
            Infleet AI Assistant
          </h2>
          <span className="relative flex h-2.5 w-2.5">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
            <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-green-500"></span>
          </span>
        </div>
      </header>

      {/* Chat History Area */}
      <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-6">
        {/* AI Message */}
        <div className="flex justify-start">
          <div className="bg-white border border-slate-200 text-slate-900 text-sm p-3.5 rounded-md rounded-tl-none max-w-[85%] shadow-sm leading-relaxed">
            Hello! I'm the Infleet AI Support Agent. How can I help you with
            your device today?
          </div>
        </div>

        {/* User Message */}
        <div className="flex justify-end">
          <div className="bg-blue-900 text-white text-sm p-3.5 rounded-md rounded-tr-none max-w-[85%] shadow-sm leading-relaxed">
            My GPS tracker screen is cracked.
          </div>
        </div>
      </div>

      {/* Input Area */}
      <div className="p-4 bg-white border-t border-slate-200 shrink-0">
        <form onSubmit={handleSubmit} className="flex gap-2">
          <input
            type="text"
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            placeholder="Type your message..."
            className="flex-1 border border-slate-300 rounded-sm px-3.5 py-2.5 text-sm focus:outline-none focus:border-blue-900 focus:ring-1 focus:ring-blue-900 placeholder:text-slate-400 transition-shadow" />
          
          <button
            type="submit"
            disabled={!inputValue.trim()}
            className="bg-blue-900 hover:bg-blue-800 disabled:bg-slate-300 disabled:text-slate-500 text-white px-4 py-2.5 rounded-sm transition-colors focus:outline-none focus:ring-2 focus:ring-blue-900 focus:ring-offset-2 flex items-center justify-center"
            aria-label="Send message">
            
            <Send
              size={18}
              strokeWidth={2}
              className={inputValue.trim() ? 'translate-x-0.5' : ''} />
            
          </button>
        </form>
      </div>
    </div>);

}