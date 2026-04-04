import React from 'react';
import ChatPanel from './components/ChatPanel.jsx';
import BoardPreview from './components/BoardPreview.jsx';
import ComponentList from './components/ComponentList.jsx';
import SimulationPanel from './components/SimulationPanel.jsx';
import ExportPanel from './components/ExportPanel.jsx';

export default function App() {
  return (
    <div className="flex h-screen bg-slate-900 text-slate-100 overflow-hidden">
      {/* Left: Chat — primary interaction surface */}
      <div className="w-1/3 min-w-80 border-r border-slate-700 flex flex-col">
        <ChatPanel />
      </div>

      {/* Right: Board + Component + Sim/Export panels */}
      <div className="flex flex-col flex-1 min-w-0">
        {/* Board preview — top ~40% */}
        <div className="flex-[2] border-b border-slate-700 min-h-0">
          <BoardPreview />
        </div>

        {/* Component list — middle */}
        <div className="flex-[1] border-b border-slate-700 min-h-0">
          <ComponentList />
        </div>

        {/* Simulation + Export — bottom row */}
        <div className="flex-[1] flex min-h-0">
          <div className="flex-1 border-r border-slate-700 min-w-0">
            <SimulationPanel />
          </div>
          <div className="flex-1 min-w-0">
            <ExportPanel />
          </div>
        </div>
      </div>
    </div>
  );
}
