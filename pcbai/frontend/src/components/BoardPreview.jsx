import React from 'react';
import { useKiCadState } from '../hooks/useKiCadState.js';

export default function BoardPreview() {
  const { boardState, isConnected } = useKiCadState();

  return (
    <div className="flex flex-col h-full">
      <div className="px-4 py-2 border-b border-slate-700 bg-slate-800 flex items-center justify-between">
        <h2 className="text-xs font-semibold text-slate-300 uppercase tracking-wider">Board Preview</h2>
        <span className={`text-xs px-2 py-0.5 rounded-full ${isConnected ? 'bg-green-900 text-green-300' : 'bg-slate-700 text-slate-400'}`}>
          {isConnected ? 'KiCad Connected' : 'Not Connected'}
        </span>
      </div>
      <div className="flex-1 flex items-center justify-center bg-slate-950">
        {boardState ? (
          <p className="text-slate-400 text-sm">Board state loaded</p>
        ) : (
          <div className="text-center text-slate-600">
            <svg className="w-16 h-16 mx-auto mb-3 opacity-30" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <rect x="2" y="2" width="20" height="20" rx="2" strokeWidth="1.5" />
              <path d="M7 7h4v4H7zM13 7h4v4h-4zM7 13h4v4H7zM13 13h4v4h-4z" strokeWidth="1" />
            </svg>
            <p className="text-sm">Board preview will appear here</p>
            <p className="text-xs mt-1">Start chatting to design your PCB</p>
          </div>
        )}
      </div>
    </div>
  );
}
