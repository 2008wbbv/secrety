import React, { useState, useRef, useEffect } from 'react';
import { useClaudeStream } from '../hooks/useClaudeStream.js';

const STAGE_LABELS = {
  intent_capture:        'Intent',
  component_resolution:  'Components',
  datasheet_ingestion:   'Datasheets',
  constraint_generation: 'Constraints',
  simulation_precheck:   'Simulation',
  kicad_layout:          'Layout',
  drc_loop:              'DRC',
  spice_generation:      'SPICE',
  final_review:          'Review',
  export:                'Export',
};

const STAGE_ORDER = Object.keys(STAGE_LABELS);

const EXPERTISE_COLORS = {
  unknown:  'text-slate-400',
  beginner: 'text-green-400',
  expert:   'text-blue-400',
  mixed:    'text-yellow-400',
};

export default function ChatPanel() {
  const [input, setInput] = useState('');
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);
  const {
    messages,
    isStreaming,
    error,
    expertiseLevel,
    stage,
    sendMessage,
    cancelStream,
    clearMessages,
  } = useClaudeStream();

  // Auto-scroll to bottom on new content
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Re-focus input after streaming completes
  useEffect(() => {
    if (!isStreaming) inputRef.current?.focus();
  }, [isStreaming]);

  function handleSubmit(e) {
    e.preventDefault();
    const text = input.trim();
    if (!text || isStreaming) return;
    setInput('');
    sendMessage(text);
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  }

  const stageIndex = STAGE_ORDER.indexOf(stage);

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-4 py-3 border-b border-slate-700 bg-slate-800 shrink-0">
        <div className="flex items-center justify-between">
          <h1 className="text-sm font-bold text-slate-100">PCB.AI</h1>
          <div className="flex items-center gap-2">
            <span className={`text-xs font-medium ${EXPERTISE_COLORS[expertiseLevel] ?? 'text-slate-400'}`}>
              {expertiseLevel !== 'unknown' ? expertiseLevel : ''}
            </span>
            {messages.length > 0 && (
              <button
                onClick={clearMessages}
                title="Clear conversation"
                className="text-slate-500 hover:text-slate-300 text-xs transition-colors"
              >
                clear
              </button>
            )}
          </div>
        </div>

        {/* Stage progress bar */}
        <div className="mt-2 flex gap-0.5">
          {STAGE_ORDER.map((s, i) => (
            <div
              key={s}
              title={STAGE_LABELS[s]}
              className={`h-1 flex-1 rounded-full transition-colors ${
                i < stageIndex
                  ? 'bg-blue-500'
                  : i === stageIndex
                  ? 'bg-blue-400'
                  : 'bg-slate-700'
              }`}
            />
          ))}
        </div>
        <p className="text-xs text-slate-500 mt-1">{STAGE_LABELS[stage] ?? stage}</p>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4 min-h-0">
        {messages.length === 0 && !error && (
          <div className="text-center text-slate-600 mt-8 px-4">
            <p className="text-sm mb-2">Tell me what you want to build.</p>
            <p className="text-xs leading-relaxed">
              e.g. "A 3D printer controller with TMC2209 drivers, ESP32, and 24V input"
            </p>
          </div>
        )}

        {messages.map((msg) => (
          <MessageBubble key={msg.id} message={msg} />
        ))}

        {error && (
          <div className="rounded-lg border border-red-800 bg-red-950 px-3 py-2 text-xs text-red-300">
            {error}
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input area */}
      <div className="px-4 py-3 border-t border-slate-700 bg-slate-800 shrink-0">
        <form onSubmit={handleSubmit} className="flex gap-2 items-end">
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => {
              setInput(e.target.value);
              // Auto-resize
              e.target.style.height = 'auto';
              e.target.style.height = Math.min(e.target.scrollHeight, 120) + 'px';
            }}
            onKeyDown={handleKeyDown}
            placeholder={isStreaming ? 'Claude is thinking…' : 'Describe your board…'}
            disabled={isStreaming}
            rows={1}
            className="flex-1 bg-slate-700 text-slate-100 placeholder-slate-500 rounded-lg px-3 py-2 text-sm border border-slate-600 focus:outline-none focus:border-blue-500 disabled:opacity-50 resize-none overflow-hidden"
          />
          {isStreaming ? (
            <button
              type="button"
              onClick={cancelStream}
              className="bg-red-700 hover:bg-red-600 text-white rounded-lg px-3 py-2 text-sm font-medium transition-colors shrink-0"
            >
              Stop
            </button>
          ) : (
            <button
              type="submit"
              disabled={!input.trim()}
              className="bg-blue-600 hover:bg-blue-500 disabled:bg-slate-700 disabled:cursor-not-allowed text-white rounded-lg px-4 py-2 text-sm font-medium transition-colors shrink-0"
            >
              Send
            </button>
          )}
        </form>
      </div>
    </div>
  );
}

// ── Message bubble ────────────────────────────────────────────────────────────

function MessageBubble({ message }) {
  const isUser = message.role === 'user';

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[90%] rounded-2xl px-3 py-2 text-sm leading-relaxed ${
          isUser
            ? 'bg-blue-600 text-white rounded-br-md'
            : 'bg-slate-700 text-slate-100 rounded-bl-md'
        }`}
      >
        {/* Render content with basic markdown-like formatting */}
        <MessageContent content={message.content} />
        {message.streaming && (
          <span className="inline-block w-1.5 h-4 bg-slate-400 animate-pulse ml-0.5 align-middle rounded-sm" />
        )}
      </div>
    </div>
  );
}

// ── Message content (minimal markdown) ───────────────────────────────────────

function MessageContent({ content }) {
  if (!content) return null;

  // Split on code blocks first, then process text
  const parts = content.split(/(```[\s\S]*?```)/g);

  return (
    <div className="space-y-2">
      {parts.map((part, i) => {
        if (part.startsWith('```')) {
          const lines = part.split('\n');
          const lang = lines[0].slice(3).trim();
          const code = lines.slice(1, -1).join('\n');
          return (
            <pre key={i} className="bg-slate-900 rounded-lg px-3 py-2 text-xs overflow-x-auto font-mono text-slate-300">
              {lang && <div className="text-slate-500 text-xs mb-1">{lang}</div>}
              {code}
            </pre>
          );
        }
        // Inline text: handle **bold** and `code`
        return <InlineText key={i} text={part} />;
      })}
    </div>
  );
}

function InlineText({ text }) {
  // Split paragraphs
  const paragraphs = text.split(/\n\n+/);
  return (
    <>
      {paragraphs.map((para, i) => {
        const lines = para.split('\n');
        return (
          <p key={i} className="whitespace-pre-wrap break-words">
            {lines.map((line, j) => (
              <React.Fragment key={j}>
                {j > 0 && <br />}
                <InlineLine line={line} />
              </React.Fragment>
            ))}
          </p>
        );
      })}
    </>
  );
}

function InlineLine({ line }) {
  // Handle **bold** and `code` inline
  const tokens = line.split(/(\*\*[^*]+\*\*|`[^`]+`)/g);
  return (
    <>
      {tokens.map((token, i) => {
        if (token.startsWith('**') && token.endsWith('**')) {
          return <strong key={i} className="font-semibold">{token.slice(2, -2)}</strong>;
        }
        if (token.startsWith('`') && token.endsWith('`')) {
          return <code key={i} className="bg-slate-800 px-1 rounded text-xs font-mono text-blue-300">{token.slice(1, -1)}</code>;
        }
        return <React.Fragment key={i}>{token}</React.Fragment>;
      })}
    </>
  );
}
