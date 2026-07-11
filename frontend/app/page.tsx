'use client';

import React, { useEffect, useState } from 'react';
import { Header } from '../components/Header';
import { MetricsCards } from '../components/MetricsCards';
import { RunList } from '../components/RunList';
import { RunDetail } from '../components/RunDetail';
import {
  approveRunAction,
  createRun,
  getHealth,
  getMetrics,
  getRun,
  getRuns,
  Metrics,
  Run,
} from '../lib/api';

const SAMPLE_PROMPTS = [
  'Analyze our sales data, identify why revenue dropped, and find top-performing products.',
  'Why did sales decline in Q3/Q4? Break down performance by region and explain what happened.',
  'Analyze the revenue drop and email the summary report to vp_sales@company.com for review.',
];

export default function DashboardPage() {
  const [apiKey, setApiKey] = useState('dev-admin-key');
  const [systemStatus, setSystemStatus] = useState('connecting');
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [runs, setRuns] = useState<Run[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [selectedRun, setSelectedRun] = useState<Run | null>(null);
  const [prompt, setPrompt] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isApproving, setIsApproving] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const loadData = async () => {
    try {
      const [health, met, allRuns] = await Promise.all([
        getHealth().catch(() => ({ status: 'offline' })),
        getMetrics(apiKey).catch(() => null),
        getRuns(apiKey).catch(() => []),
      ]);
      setSystemStatus(health.status || 'unknown');
      setMetrics(met);
      setRuns(allRuns);
      if (allRuns.length > 0 && !selectedRunId) {
        setSelectedRunId(allRuns[0].id);
      }
    } catch (err: any) {
      console.error(err);
    }
  };

  useEffect(() => {
    loadData();
    const timer = setInterval(loadData, 8000);
    return () => clearInterval(timer);
  }, [apiKey]);

  useEffect(() => {
    if (!selectedRunId) {
      setSelectedRun(null);
      return;
    }
    getRun(selectedRunId, apiKey)
      .then(setSelectedRun)
      .catch((err) => console.error(err));
  }, [selectedRunId, apiKey]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!prompt.trim() || isSubmitting) return;

    setIsSubmitting(true);
    setErrorMsg(null);
    try {
      const res = await createRun(prompt.trim(), false, apiKey);
      setPrompt('');
      await loadData();
      if (res.run_id) {
        setSelectedRunId(res.run_id);
      }
    } catch (err: any) {
      setErrorMsg(err.message || 'Submission failed');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleApprove = async (id: string, decision: 'approve' | 'reject', notes?: string) => {
    setIsApproving(true);
    try {
      await approveRunAction(id, decision, notes, apiKey);
      await loadData();
      const updated = await getRun(id, apiKey);
      setSelectedRun(updated);
    } catch (err: any) {
      alert(`Approval error: ${err.message}`);
    } finally {
      setIsApproving(false);
    }
  };

  return (
    <div className="min-h-screen flex flex-col bg-slate-950">
      <Header
        apiKey={apiKey}
        onApiKeyChange={setApiKey}
        systemStatus={systemStatus}
      />

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 w-full flex-1 flex flex-col">
        {/* Metrics Bar */}
        <MetricsCards metrics={metrics} />

        {/* Prompt Input Box */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 sm:p-5 mb-6 shadow-sm">
          <form onSubmit={handleSubmit} className="space-y-3">
            <div className="flex items-center justify-between">
              <label className="text-xs font-semibold text-slate-300">
                Ask a Business Analysis Question
              </label>
              <span className="text-[11px] text-slate-500">
                Orchestrates Planner · Data Analyst · Researcher · Insight · Reviewer · Report
              </span>
            </div>

            <div className="flex flex-col sm:flex-row gap-2">
              <input
                type="text"
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                placeholder="e.g. Analyze our sales data, identify why revenue dropped, and find top-performing products..."
                className="flex-1 bg-slate-950 border border-slate-700/80 rounded-lg px-4 py-2.5 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-sky-500 transition"
              />
              <button
                type="submit"
                disabled={isSubmitting || !prompt.trim()}
                className="px-5 py-2.5 bg-sky-500 hover:bg-sky-400 text-slate-950 font-semibold text-xs rounded-lg transition disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center space-x-1.5 shadow-sm"
              >
                {isSubmitting ? (
                  <>
                    <span className="inline-block animate-spin h-3.5 w-3.5 border-2 border-slate-950 border-t-transparent rounded-full" />
                    <span>Executing Workflow...</span>
                  </>
                ) : (
                  <span>Submit Question</span>
                )}
              </button>
            </div>

            {errorMsg && (
              <p className="text-xs text-rose-400 bg-rose-500/10 border border-rose-500/20 p-2 rounded">
                {errorMsg}
              </p>
            )}

            {/* Quick Prompts */}
            <div className="flex flex-wrap items-center gap-1.5 pt-1">
              <span className="text-[11px] text-slate-500 mr-1">Quick examples:</span>
              {SAMPLE_PROMPTS.map((p, idx) => (
                <button
                  key={idx}
                  type="button"
                  onClick={() => setPrompt(p)}
                  className="text-[11px] bg-slate-800/80 hover:bg-slate-800 text-slate-300 px-2.5 py-1 rounded-md border border-slate-700/50 transition truncate max-w-[280px]"
                >
                  {p}
                </button>
              ))}
            </div>
          </form>
        </div>

        {/* 2-Column Workspace: History & Run Detail */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 flex-1 items-start">
          <div className="lg:col-span-4">
            <RunList
              runs={runs}
              selectedId={selectedRunId}
              onSelect={setSelectedRunId}
              isLoading={false}
            />
          </div>
          <div className="lg:col-span-8 h-full">
            <RunDetail
              run={selectedRun}
              onApprove={handleApprove}
              isApproving={isApproving}
            />
          </div>
        </div>
      </main>
    </div>
  );
}
