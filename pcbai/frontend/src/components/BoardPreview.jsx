import React from 'react';
import { useKiCadState } from '../hooks/useKiCadState.js';

export default function BoardPreview() {
  const { boardState, isConnected, queueDepth, drcIteration } = useKiCadState();

  const componentCount = boardState?.components?.length ?? 0;
  const traceCount = boardState?.traces?.length ?? 0;
  const netCount = boardState?.nets?.length ?? 0;

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-4 py-2 border-b border-slate-700 bg-slate-800 flex items-center justify-between gap-2 flex-wrap">
        <h2 className="text-xs font-semibold text-slate-300 uppercase tracking-wider">Board Preview</h2>
        <div className="flex items-center gap-2">
          {queueDepth > 0 && (
            <span className="text-xs bg-yellow-900 text-yellow-300 px-2 py-0.5 rounded-full">
              {queueDepth} queued
            </span>
          )}
          {drcIteration > 0 && (
            <span className="text-xs bg-purple-900 text-purple-300 px-2 py-0.5 rounded-full">
              DRC #{drcIteration}
            </span>
          )}
          <span className={`text-xs px-2 py-0.5 rounded-full ${
            isConnected ? 'bg-green-900 text-green-300' : 'bg-slate-700 text-slate-400'
          }`}>
            {isConnected ? 'KiCad Connected' : 'Not Connected'}
          </span>
        </div>
      </div>

      {/* Board stats (when connected) */}
      {isConnected && boardState && (
        <div className="flex gap-4 px-4 py-1.5 bg-slate-900 border-b border-slate-700 text-xs text-slate-400">
          <span>{componentCount} components</span>
          <span>{traceCount} traces</span>
          <span>{netCount} nets</span>
          {boardState.width_mm > 0 && (
            <span>{boardState.width_mm} × {boardState.height_mm} mm</span>
          )}
        </div>
      )}

      {/* Canvas area */}
      <div className="flex-1 flex items-center justify-center bg-slate-950">
        {boardState && componentCount > 0 ? (
          <div className="w-full h-full p-4 overflow-auto">
            {/* Minimal component list as placeholder for real board canvas (Step 8) */}
            <div className="text-xs text-slate-400 space-y-1">
              {boardState.components.map((c) => (
                <div key={c.ref} className="flex gap-3 font-mono">
                  <span className="text-blue-400 w-12 shrink-0">{c.ref}</span>
                  <span className="text-slate-300 w-20 shrink-0">{c.value}</span>
                  <span className="text-slate-500">
                    ({c.x_mm}, {c.y_mm}) mm
                  </span>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <div className="text-center text-slate-600">
            <svg className="w-16 h-16 mx-auto mb-3 opacity-30" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <rect x="2" y="2" width="20" height="20" rx="2" strokeWidth="1.5" />
              <circle cx="8" cy="8" r="1.5" strokeWidth="1" />
              <circle cx="16" cy="8" r="1.5" strokeWidth="1" />
              <circle cx="8" cy="16" r="1.5" strokeWidth="1" />
              <circle cx="16" cy="16" r="1.5" strokeWidth="1" />
              <line x1="9.5" y1="8" x2="14.5" y2="8" strokeWidth="0.75" />
              <line x1="8" y1="9.5" x2="8" y2="14.5" strokeWidth="0.75" />
            </svg>
            <p className="text-sm">Board preview will appear here</p>
            <p className="text-xs mt-1 text-slate-700">
              {isConnected ? 'No board loaded' : 'KiCad not connected'}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
