'use client';

import React, { useState } from 'react';
import { Run } from '../lib/api';

interface RunDetailProps {
  run: Run | null;
  onApprove: (id: string, decision: 'approve' | 'reject', notes?: string) => Promise<void>;
  isApproving: boolean;
}

export function RunDetail({ run, onApprove, isApproving }: RunDetailProps) {
  const [activeTab, setActiveTab] = useState<'report' | 'timeline' | 'verification' | 'action'>('report');
  const [approvalNotes, setApprovalNotes] = useState('');

  if (!run) {
    return (
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-12 text-center text-slate-500">
        Select a run from the history to view executive reports, agent graphs, and approval gates.
      </div>
    );
  }

  const hasPendingAction =
    run.external_action &&
    (run.external_action.status === 'pending_approval' || run.external_action.status === 'pending');

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-sm flex flex-col h-full">
      {/* Top Banner */}
      <div className="p-5 border-b border-slate-800 bg-slate-900/50">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="flex items-center space-x-2">
              <span className="font-mono text-sm font-bold text-sky-400">{run.id}</span>
              <span className="text-xs px-2.5 py-0.5 rounded-full font-medium bg-slate-800 border border-slate-700 text-slate-300">
                {run.status}
              </span>
            </div>
            <p className="text-xs text-slate-400 mt-1">
              Started by <span className="text-slate-200 font-medium">{run.user}</span> at{' '}
              {new Date(run.created_at).toLocaleString()}
            </p>
          </div>

          {/* Quick Metrics */}
          {run.metrics && (
            <div className="flex items-center space-x-4 text-xs font-mono text-slate-300">
              <div className="bg-slate-800/80 px-2.5 py-1 rounded border border-slate-700/60">
                <span className="text-slate-500">Duration: </span>
                <span>{((run.metrics.duration_ms || 0) / 1000).toFixed(2)}s</span>
              </div>
              <div className="bg-slate-800/80 px-2.5 py-1 rounded border border-slate-700/60">
                <span className="text-slate-500">Tool Calls: </span>
                <span>{run.metrics.tool_calls_count || 0}</span>
              </div>
            </div>
          )}
        </div>

        {/* Human in the loop Approval Callout */}
        {hasPendingAction && (
          <div className="mt-4 p-4 rounded-lg bg-amber-500/10 border border-amber-500/30 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
            <div>
              <p className="text-xs font-bold text-amber-400 uppercase tracking-wide">
                Human Approval Required
              </p>
              <p className="text-xs text-amber-200/90 mt-0.5">
                The agent proposes an external {run.external_action.type} action to{' '}
                <span className="font-semibold text-white">{run.external_action.recipient || 'unspecified'}</span>.
              </p>
            </div>
            <div className="flex items-center space-x-2 w-full sm:w-auto">
              <button
                disabled={isApproving}
                onClick={() => onApprove(run.id, 'reject', approvalNotes)}
                className="px-3 py-1.5 text-xs font-medium bg-rose-500/20 text-rose-300 border border-rose-500/40 rounded-lg hover:bg-rose-500/30 transition disabled:opacity-50"
              >
                Reject
              </button>
              <button
                disabled={isApproving}
                onClick={() => onApprove(run.id, 'approve', approvalNotes)}
                className="px-4 py-1.5 text-xs font-medium bg-emerald-500 text-slate-950 font-semibold rounded-lg hover:bg-emerald-400 transition disabled:opacity-50 shadow-sm"
              >
                Approve & Dispatch
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Tabs */}
      <div className="flex border-b border-slate-800 px-4 bg-slate-950/40">
        <button
          onClick={() => setActiveTab('report')}
          className={`py-3 px-3 text-xs font-medium border-b-2 transition ${
            activeTab === 'report'
              ? 'border-sky-500 text-sky-400'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          Executive Report
        </button>
        <button
          onClick={() => setActiveTab('timeline')}
          className={`py-3 px-3 text-xs font-medium border-b-2 transition ${
            activeTab === 'timeline'
              ? 'border-sky-500 text-sky-400'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          Agent Execution Timeline ({run.events?.length || 0})
        </button>
        <button
          onClick={() => setActiveTab('verification')}
          className={`py-3 px-3 text-xs font-medium border-b-2 transition ${
            activeTab === 'verification'
              ? 'border-sky-500 text-sky-400'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          Verification & Checks
        </button>
        {run.external_action && (
          <button
            onClick={() => setActiveTab('action')}
            className={`py-3 px-3 text-xs font-medium border-b-2 transition ${
              activeTab === 'action'
                ? 'border-sky-500 text-sky-400'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            External Action
          </button>
        )}
      </div>

      {/* Tab Contents */}
      <div className="p-6 flex-1 overflow-y-auto max-h-[560px]">
        {activeTab === 'report' && (
          <div>
            {run.report_markdown ? (
              <div className="prose prose-invert prose-sm max-w-none space-y-4">
                <pre className="whitespace-pre-wrap font-sans text-xs text-slate-200 leading-relaxed bg-slate-950/50 p-5 rounded-lg border border-slate-800">
                  {run.report_markdown}
                </pre>
              </div>
            ) : (
              <div className="text-center py-12 text-slate-500 text-xs">
                No report has been assembled for this run yet.
              </div>
            )}
          </div>
        )}

        {activeTab === 'timeline' && (
          <div className="space-y-3">
            {(run.events || []).map((ev, i) => (
              <div key={i} className="flex items-start space-x-3 text-xs">
                <span className="font-mono text-slate-500 text-[10px] min-w-[70px] pt-0.5">
                  {new Date(ev.ts).toLocaleTimeString()}
                </span>
                <span
                  className={`px-2 py-0.5 rounded font-mono text-[10px] font-semibold border ${
                    ev.agent === 'reviewer'
                      ? 'bg-purple-500/10 text-purple-400 border-purple-500/20'
                      : ev.agent === 'data_analyst'
                      ? 'bg-sky-500/10 text-sky-400 border-sky-500/20'
                      : ev.agent === 'researcher'
                      ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
                      : ev.agent === 'planner'
                      ? 'bg-amber-500/10 text-amber-400 border-amber-500/20'
                      : 'bg-slate-800 text-slate-300 border-slate-700'
                  }`}
                >
                  {ev.agent}
                </span>
                <p className="text-slate-300 flex-1">{ev.message}</p>
              </div>
            ))}
          </div>
        )}

        {activeTab === 'verification' && (
          <div className="space-y-4">
            {run.result?.review_result ? (
              <div>
                <div className="flex items-center space-x-3 mb-4">
                  <span
                    className={`px-3 py-1 text-xs font-bold rounded-lg border ${
                      run.result.review_result.passed
                        ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
                        : 'bg-rose-500/10 text-rose-400 border-rose-500/30'
                    }`}
                  >
                    Verification Result: {run.result.review_result.passed ? 'PASSED' : 'FAILED'}
                  </span>
                </div>
                <div className="border border-slate-800 rounded-lg overflow-hidden">
                  <table className="w-full text-xs text-left">
                    <thead className="bg-slate-950 text-slate-400 border-b border-slate-800">
                      <tr>
                        <th className="p-2.5">Check Name</th>
                        <th className="p-2.5">Outcome</th>
                        <th className="p-2.5">Evidence & Validation Detail</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800 text-slate-300">
                      {(run.result.review_result.checks || []).map((chk: any, i: number) => (
                        <tr key={i} className="hover:bg-slate-800/30">
                          <td className="p-2.5 font-mono text-slate-400">{chk.name}</td>
                          <td className="p-2.5">
                            <span
                              className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                                chk.passed ? 'text-emerald-400' : 'text-rose-400'
                              }`}
                            >
                              {chk.passed ? 'PASS' : 'FAIL'}
                            </span>
                          </td>
                          <td className="p-2.5 text-slate-300">{chk.detail}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            ) : (
              <p className="text-slate-500 text-xs">Verification data unavailable.</p>
            )}
          </div>
        )}

        {activeTab === 'action' && run.external_action && (
          <div className="space-y-4 text-xs">
            <div className="bg-slate-950 p-4 rounded-lg border border-slate-800 space-y-2">
              <div className="flex justify-between">
                <span className="text-slate-500">Action Type:</span>
                <span className="text-sky-400 font-semibold">{run.external_action.type}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Recipient:</span>
                <span className="text-slate-200">{run.external_action.recipient || 'N/A'}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Approval Status:</span>
                <span className="text-amber-400">{run.external_action.status}</span>
              </div>
              {run.external_action.approved_by && (
                <div className="flex justify-between">
                  <span className="text-slate-500">Approved By:</span>
                  <span className="text-emerald-400">{run.external_action.approved_by}</span>
                </div>
              )}
            </div>
            {run.external_action.delivery_result && (
              <div>
                <p className="text-slate-400 font-medium mb-1">Automation Delivery Result (n8n):</p>
                <pre className="bg-slate-950 p-3 rounded-lg border border-slate-800 text-[11px] text-slate-300 font-mono">
                  {JSON.stringify(run.external_action.delivery_result, null, 2)}
                </pre>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
