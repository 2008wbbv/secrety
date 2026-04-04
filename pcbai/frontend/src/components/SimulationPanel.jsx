import React from 'react';

export default function SimulationPanel({ results = [] }) {
  const hasFailures = results.some((r) => !r.passed);

  return (
    <div className="flex flex-col h-full">
      <div className="px-4 py-2 border-b border-slate-700 bg-slate-800 flex items-center justify-between">
        <h2 className="text-xs font-semibold text-slate-300 uppercase tracking-wider">Simulation</h2>
        {results.length > 0 && (
          <span className={`text-xs px-2 py-0.5 rounded-full ${hasFailures ? 'bg-red-900 text-red-300' : 'bg-green-900 text-green-300'}`}>
            {hasFailures ? 'Issues Found' : 'All Pass'}
          </span>
        )}
      </div>
      <div className="flex-1 overflow-y-auto px-4 py-3">
        {results.length === 0 ? (
          <div className="flex items-center justify-center h-full text-slate-600 text-sm">
            Simulation results will appear here
          </div>
        ) : (
          <div className="space-y-2">
            {results.map((result, i) => (
              <div
                key={i}
                className={`rounded p-2 text-xs border ${
                  result.passed
                    ? 'bg-green-950 border-green-800 text-green-300'
                    : 'bg-red-950 border-red-800 text-red-300'
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="font-medium">{result.check}</span>
                  <span>{result.passed ? '✓ Pass' : '✗ Fail'}</span>
                </div>
                {result.detail && (
                  <p className="mt-1 text-slate-400">{result.detail}</p>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
