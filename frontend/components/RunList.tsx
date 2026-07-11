'use client';

import React from 'react';
import { Run } from '../lib/api';

interface RunListProps {
  runs: Run[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  isLoading: boolean;
}

export function RunList({ runs, selectedId, onSelect, isLoading }: RunListProps) {
  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'completed':
        return 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20';
      case 'report_ready':
        return 'bg-sky-500/10 text-sky-400 border-sky-500/20';
      case 'running':
        return 'bg-indigo-500/10 text-indigo-400 border-indigo-500/20 animate-pulse';
      case 'action_rejected':
        return 'bg-amber-500/10 text-amber-400 border-amber-500/20';
      case 'failed':
      case 'review_failed':
        return 'bg-rose-500/10 text-rose-400 border-rose-500/20';
      default:
        return 'bg-slate-800 text-slate-400 border-slate-700';
    }
  };

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-sm">
      <div className="px-4 py-3 border-b border-slate-800 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-white">Execution History</h3>
        <span className="text-xs text-slate-400">{runs.length} runs</span>
      </div>

      <div className="divide-y divide-slate-800/60 max-h-[540px] overflow-y-auto">
        {isLoading && runs.length === 0 ? (
          <div className="p-8 text-center text-sm text-slate-400">Loading runs...</div>
        ) : runs.length === 0 ? (
          <div className="p-8 text-center text-sm text-slate-500">No runs recorded yet. Submit a prompt above!</div>
        ) : (
          runs.map((r) => {
            const isSelected = r.id === selectedId;
            const dateStr = new Date(r.created_at).toLocaleTimeString();
            return (
              <button
                key={r.id}
                onClick={() => onSelect(r.id)}
                className={`w-full text-left p-3.5 transition flex flex-col space-y-1.5 ${
                  isSelected
                    ? 'bg-sky-950/40 border-l-4 border-sky-500 pl-2.5'
                    : 'hover:bg-slate-800/50'
                }`}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center space-x-2">
                    <span className="font-mono text-xs font-semibold text-slate-300">{r.id}</span>
                    <span className="text-[11px] text-slate-500">by {r.user}</span>
                  </div>
                  <span
                    className={`text-[10px] font-medium px-2 py-0.5 rounded-full border ${getStatusBadge(
                      r.status
                    )}`}
                  >
                    {r.status}
                  </span>
                </div>

                <p className="text-xs text-slate-300 line-clamp-2 leading-relaxed">
                  {r.request}
                </p>

                <div className="flex items-center justify-between text-[11px] text-slate-500 pt-0.5">
                  <span>{dateStr}</span>
                  {r.metrics?.duration_ms && (
                    <span>{(r.metrics.duration_ms / 1000).toFixed(1)}s</span>
                  )}
                </div>
              </button>
            );
          })
        )}
      </div>
    </div>
  );
}
