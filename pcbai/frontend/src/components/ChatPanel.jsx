import React, { useState, useRef, useEffect } from 'react';
import { useClaudeStream } from '../hooks/useClaudeStream.js';

export default function ChatPanel() {
  const [input, setInput] = useState('');
  const messagesEndRef = useRef(null);
  const { messages, isStreaming, sendMessage } = useClaudeStream();

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  function handleSubmit(e) {
    e.preventDefault();
    const text = input.trim();
    if (!text || isStreaming) return;
    setInput('');
    sendMessage(text);
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-4 py-3 border-b border-slate-700 bg-slate-800">
        <h1 className="text-sm font-semibold text-slate-200 tracking-wide">PCB.AI</h1>
        <p className="text-xs text-slate-400 mt-0.5">Describe your board to get started</p>
      </div>

      {/* Message list */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3">
        {messages.length === 0 && (
          <div className="text-slate-500 text-sm text-center mt-8">
            <p className="mb-2">Tell me what you want to build.</p>
            <p className="text-xs">e.g. "A 3D printer controller with TMC2209 drivers and ESP32"</p>
          </div>
        )}
        {messages.map((msg, i) => (
          <div
            key={i}
            className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div
              className={`max-w-[85%] rounded-lg px-3 py-2 text-sm ${
                msg.role === 'user'
                  ? 'bg-blue-600 text-white'
                  : 'bg-slate-700 text-slate-100'
              }`}
            >
              {msg.content}
            </div>
          </div>
        ))}
        {isStreaming && (
          <div className="flex justify-start">
            <div className="bg-slate-700 text-slate-100 rounded-lg px-3 py-2 text-sm">
              <span className="animate-pulse">...</span>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <form onSubmit={handleSubmit} className="px-4 py-3 border-t border-slate-700 bg-slate-800">
        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Describe your board..."
            disabled={isStreaming}
            className="flex-1 bg-slate-700 text-slate-100 placeholder-slate-400 rounded-lg px-3 py-2 text-sm border border-slate-600 focus:outline-none focus:border-blue-500 disabled:opacity-50"
          />
          <button
            type="submit"
            disabled={!input.trim() || isStreaming}
            className="bg-blue-600 hover:bg-blue-500 disabled:bg-slate-600 disabled:cursor-not-allowed text-white rounded-lg px-4 py-2 text-sm font-medium transition-colors"
          >
            Send
          </button>
        </div>
      </form>
    </div>
  );
}
