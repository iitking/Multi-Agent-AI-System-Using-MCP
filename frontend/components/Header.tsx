'use client';

import React from 'react';

interface HeaderProps {
  apiKey: string;
  onApiKeyChange: (key: string) => void;
  systemStatus: string;
}

export function Header({ apiKey, onApiKeyChange, systemStatus }: HeaderProps) {
  return (
    <header className="border-b border-slate-800 bg-slate-900/80 backdrop-blur sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        <div className="flex items-center space-x-3">
          <div className="h-9 w-9 rounded-lg bg-sky-500/20 border border-sky-400/40 flex items-center justify-center text-sky-400 font-bold text-lg">
            AI
          </div>
          <div>
            <h1 className="text-base font-semibold text-white tracking-tight leading-tight">
              Enterprise Multi-Agent Platform
            </h1>
            <p className="text-xs text-slate-400">Model Context Protocol (MCP) · LangGraph · n8n</p>
          </div>
        </div>

        <div className="flex items-center space-x-4">
          <div className="flex items-center space-x-2 text-xs">
            <span
              className={`h-2.5 w-2.5 rounded-full ${
                systemStatus === 'ok' ? 'bg-emerald-500 shadow-sm shadow-emerald-500/50' : 'bg-amber-500'
              }`}
            />
            <span className="text-slate-300 capitalize">{systemStatus || 'Connecting...'}</span>
          </div>

          <div className="flex items-center space-x-2 bg-slate-800 border border-slate-700 rounded-lg px-2.5 py-1">
            <span className="text-xs text-slate-400">Role Key:</span>
            <select
              value={apiKey}
              onChange={(e) => onApiKeyChange(e.target.value)}
              className="bg-transparent text-xs text-sky-400 font-mono focus:outline-none cursor-pointer"
            >
              <option value="dev-admin-key" className="bg-slate-900 text-white">dev-admin-key (Admin)</option>
              <option value="dev-analyst-key" className="bg-slate-900 text-white">dev-analyst-key (Analyst)</option>
              <option value="dev-viewer-key" className="bg-slate-900 text-white">dev-viewer-key (Viewer)</option>
            </select>
          </div>
        </div>
      </div>
    </header>
  );
}
