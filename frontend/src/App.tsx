import React, { useState } from 'react';
import { SelectionScreen } from './components/SelectionScreen';
import { ChatInterface } from './components/ChatInterface';
type ScreenState = 'selection' | 'chat';
export function App() {
  const [currentScreen, setCurrentScreen] = useState<ScreenState>('selection');
  return (
    <div className="min-h-screen bg-slate-100 flex items-center justify-center p-4 sm:p-8 font-sans">
      {/*
               Widget Container
               Designed to look like a native embedded module or centered modal.
               Uses sharp corners (rounded-md), corporate borders, and deep shadows.
             */}
      <div className="w-full max-w-lg h-[600px] bg-white border border-slate-200 shadow-2xl rounded-md flex flex-col overflow-hidden relative">
        {currentScreen === 'selection' ?
        <SelectionScreen onSelectChat={() => setCurrentScreen('chat')} /> :

        <ChatInterface onBack={() => setCurrentScreen('selection')} />
        }
      </div>
    </div>);

}