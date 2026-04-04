import React, { useState } from 'react';

const EXPORT_TYPES = [
  { id: 'gerbers', label: 'Gerbers', description: 'Manufacturing files' },
  { id: 'drill', label: 'Drill Files', description: 'NC drill' },
  { id: 'bom', label: 'BOM', description: 'Bill of materials' },
  { id: 'pnp', label: 'Pick & Place', description: 'Assembly file' },
];

export default function ExportPanel({ onExport }) {
  const [exporting, setExporting] = useState(false);
  const [exported, setExported] = useState([]);

  async function handleExport() {
    if (!onExport) return;
    setExporting(true);
    try {
      const files = await onExport(EXPORT_TYPES.map((t) => t.id));
      setExported(files ?? []);
    } finally {
      setExporting(false);
    }
  }

  return (
    <div className="flex flex-col h-full">
      <div className="px-4 py-2 border-b border-slate-700 bg-slate-800">
        <h2 className="text-xs font-semibold text-slate-300 uppercase tracking-wider">Export</h2>
      </div>
      <div className="flex-1 overflow-y-auto px-4 py-3">
        <div className="space-y-1.5 mb-4">
          {EXPORT_TYPES.map((type) => (
            <div key={type.id} className="flex items-center justify-between text-xs">
              <span className="text-slate-300">{type.label}</span>
              <span className="text-slate-500">{type.description}</span>
            </div>
          ))}
        </div>

        <button
          onClick={handleExport}
          disabled={exporting || !onExport}
          className="w-full bg-blue-600 hover:bg-blue-500 disabled:bg-slate-700 disabled:cursor-not-allowed text-white rounded-lg px-4 py-2 text-sm font-medium transition-colors"
        >
          {exporting ? 'Exporting...' : 'Export All Files'}
        </button>

        {exported.length > 0 && (
          <div className="mt-3 space-y-1">
            {exported.map((file, i) => (
              <div key={i} className="text-xs text-green-400 flex items-center gap-1.5">
                <span>✓</span>
                <span className="font-mono">{file}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
