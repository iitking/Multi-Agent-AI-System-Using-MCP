'use client';

import React from 'react';
import { Metrics } from '../lib/api';

interface MetricsCardsProps {
  metrics: Metrics | null;
}

export function MetricsCards({ metrics }: MetricsCardsProps) {
  if (!metrics) return null;

  const items = [
    {
      label: 'Task Completion Rate',
      value: `${metrics.completion_rate_pct}%`,
      sub: `${metrics.completed_runs} of ${metrics.total_runs} runs`,
      highlight: 'text-emerald-400',
    },
    {
      label: 'MCP Tool Calls',
      value: metrics.total_tool_calls.toLocaleString(),
      sub: `${metrics.tool_success_rate_pct}% success rate`,
      highlight: 'text-sky-400',
    },
    {
      label: 'Average Latency',
      value: `${(metrics.avg_duration_ms / 1000).toFixed(2)}s`,
      sub: 'per multi-agent workflow',
      highlight: 'text-indigo-400',
    },
    {
      label: 'Model Execution Cost',
      value: `$${metrics.total_estimated_cost_usd.toFixed(4)}`,
      sub: 'tracked token spend',
      highlight: 'text-amber-400',
    },
  ];

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
      {items.map((item, idx) => (
        <div
          key={idx}
          className="bg-slate-900 border border-slate-800 rounded-xl p-4 shadow-sm hover:border-slate-700 transition"
        >
          <p className="text-xs font-medium text-slate-400 uppercase tracking-wider">{item.label}</p>
          <p className={`text-2xl font-bold mt-1 ${item.highlight}`}>{item.value}</p>
          <p className="text-xs text-slate-500 mt-1">{item.sub}</p>
        </div>
      ))}
    </div>
  );
}
