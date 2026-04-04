import React from 'react';

export default function ComponentList({ components = [] }) {
  return (
    <div className="flex flex-col h-full">
      <div className="px-4 py-2 border-b border-slate-700 bg-slate-800 flex items-center justify-between">
        <h2 className="text-xs font-semibold text-slate-300 uppercase tracking-wider">Components</h2>
        <span className="text-xs text-slate-500">{components.length} parts</span>
      </div>
      <div className="flex-1 overflow-y-auto">
        {components.length === 0 ? (
          <div className="flex items-center justify-center h-full text-slate-600 text-sm">
            No components yet
          </div>
        ) : (
          <table className="w-full text-xs">
            <thead className="bg-slate-800 text-slate-400 sticky top-0">
              <tr>
                <th className="px-4 py-2 text-left font-medium">Ref</th>
                <th className="px-4 py-2 text-left font-medium">Value</th>
                <th className="px-4 py-2 text-left font-medium">Package</th>
                <th className="px-4 py-2 text-left font-medium">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-700">
              {components.map((comp, i) => (
                <tr key={i} className="hover:bg-slate-800 transition-colors">
                  <td className="px-4 py-2 text-slate-300 font-mono">{comp.ref}</td>
                  <td className="px-4 py-2 text-slate-300">{comp.value}</td>
                  <td className="px-4 py-2 text-slate-400">{comp.package}</td>
                  <td className="px-4 py-2">
                    <span className={`px-1.5 py-0.5 rounded text-xs ${
                      comp.status === 'placed' ? 'bg-green-900 text-green-300' :
                      comp.status === 'error' ? 'bg-red-900 text-red-300' :
                      'bg-slate-700 text-slate-400'
                    }`}>
                      {comp.status ?? 'pending'}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
