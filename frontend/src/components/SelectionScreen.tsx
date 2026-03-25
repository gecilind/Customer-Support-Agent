import React from 'react';
import { MessageSquare, Mic } from 'lucide-react';
interface SelectionScreenProps {
  onSelectChat: () => void;
}
export function SelectionScreen({ onSelectChat }: SelectionScreenProps) {
  return (
    <div className="flex flex-col h-full p-6 sm:p-8 bg-white animate-in fade-in duration-300">
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-slate-900 mb-2 tracking-tight">
          Infleet Support
        </h1>
        <p className="text-sm text-slate-600">
          How would you like to interact with our AI Assistant?
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 flex-1 content-start">
        {/* Chatbot Card */}
        <button
          onClick={onSelectChat}
          className="flex flex-col items-start p-5 border border-slate-200 rounded-md hover:border-blue-900 hover:bg-slate-50 transition-all group focus:outline-none focus:ring-2 focus:ring-blue-900 focus:ring-offset-2 text-left bg-white shadow-sm hover:shadow-md"
          aria-label="Select Chatbot">
          
          <div className="p-2.5 bg-blue-50 text-blue-900 rounded-sm mb-4 group-hover:bg-blue-100 transition-colors">
            <MessageSquare size={24} strokeWidth={2} />
          </div>
          <h2 className="font-semibold text-slate-900 text-lg mb-1">Chatbot</h2>
          <p className="text-sm text-slate-500 leading-relaxed">
            Type your questions for instant answers.
          </p>
        </button>

        {/* Voice Agent Card (Disabled/Coming Soon) */}
        <div className="flex flex-col items-start p-5 border border-slate-200 rounded-md bg-slate-50 opacity-80 cursor-not-allowed relative">
          <div className="flex justify-between w-full items-start mb-4">
            <div className="p-2.5 bg-slate-200 text-slate-500 rounded-sm">
              <Mic size={24} strokeWidth={2} />
            </div>
            <span className="text-[10px] font-bold uppercase tracking-wider bg-slate-200 text-slate-600 px-2 py-1 rounded-sm">
              Phase 2
            </span>
          </div>
          <h2 className="font-semibold text-slate-700 text-lg mb-1">
            Voice Agent
          </h2>
          <p className="text-sm text-slate-500 leading-relaxed">
            Speak directly with our AI.
          </p>
        </div>
      </div>
    </div>);

}