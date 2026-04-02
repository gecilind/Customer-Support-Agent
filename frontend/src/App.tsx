import React, { useState } from 'react';
import { SelectionScreen } from './components/SelectionScreen';
import { ChatInterface } from './components/ChatInterface';
import { ChatHistory } from './components/ChatHistory';

type ScreenState = 'selection' | 'chat' | 'history';

export function App() {
  const [currentScreen, setCurrentScreen] = useState<ScreenState>('selection');
  const [historyConversationId, setHistoryConversationId] = useState<number | null>(null);

  return (
    <div className="min-h-screen bg-slate-100 flex items-center justify-center p-4 sm:p-8 font-sans">
      {/*
               Widget Container
               Designed to look like a native embedded module or centered modal.
               Uses sharp corners (rounded-md), corporate borders, and deep shadows.
             */}
      <div className="w-full max-w-lg h-[600px] bg-white border border-slate-200 shadow-2xl rounded-md flex flex-col overflow-hidden relative">
        {currentScreen === 'selection' ? (
          <SelectionScreen
            onSelectChat={() => setCurrentScreen('chat')}
            onSelectHistory={(id) => {
              setHistoryConversationId(id);
              setCurrentScreen('history');
            }}
          />
        ) : currentScreen === 'chat' ? (
          <ChatInterface onBack={() => setCurrentScreen('selection')} />
        ) : historyConversationId !== null ? (
          <ChatHistory
            conversationId={historyConversationId}
            onBack={() => {
              setHistoryConversationId(null);
              setCurrentScreen('selection');
            }}
          />
        ) : null}
      </div>
    </div>
  );
}
