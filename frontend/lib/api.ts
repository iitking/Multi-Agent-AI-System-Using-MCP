export interface Run {
  id: string;
  user: string;
  request: string;
  status: string;
  created_at: string;
  updated_at: string;
  plan?: any;
  result?: any;
  report_markdown?: string;
  report_path?: string;
  external_action?: any;
  metrics?: {
    duration_ms?: number;
    tool_calls_count?: number;
    tool_calls_ok?: number;
    cost_usd?: number;
    retry_count?: number;
  };
  events?: Array<{
    ts: string;
    agent: string;
    status: string;
    message: string;
  }>;
  error?: string;
}

export interface Metrics {
  total_runs: number;
  completed_runs: number;
  failed_runs: number;
  completion_rate_pct: number;
  total_tool_calls: number;
  tool_success_rate_pct: number;
  avg_duration_ms: number;
  total_estimated_cost_usd: number;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
const DEFAULT_KEY = process.env.NEXT_PUBLIC_DEFAULT_API_KEY || 'dev-admin-key';

function getHeaders(apiKey?: string): HeadersInit {
  return {
    'Content-Type': 'application/json',
    'X-API-Key': apiKey || DEFAULT_KEY,
  };
}

export async function getHealth() {
  const res = await fetch(`${API_BASE}/api/health`);
  return res.json();
}

export async function getRuns(apiKey?: string): Promise<Run[]> {
  const res = await fetch(`${API_BASE}/api/runs?limit=50`, {
    headers: getHeaders(apiKey),
  });
  if (!res.ok) throw new Error(`Failed to load runs: ${res.statusText}`);
  return res.json();
}

export async function getRun(id: string, apiKey?: string): Promise<Run> {
  const res = await fetch(`${API_BASE}/api/runs/${id}`, {
    headers: getHeaders(apiKey),
  });
  if (!res.ok) throw new Error(`Failed to load run: ${res.statusText}`);
  return res.json();
}

export async function createRun(request: string, asyncExecution: boolean = false, apiKey?: string) {
  const res = await fetch(`${API_BASE}/api/runs`, {
    method: 'POST',
    headers: getHeaders(apiKey),
    body: JSON.stringify({ request, async_execution: asyncExecution }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || 'Failed to submit run');
  }
  return res.json();
}

export async function approveRunAction(
  id: string,
  decision: 'approve' | 'reject',
  notes?: string,
  apiKey?: string
) {
  const res = await fetch(`${API_BASE}/api/runs/${id}/approve`, {
    method: 'POST',
    headers: getHeaders(apiKey),
    body: JSON.stringify({ decision, notes }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || 'Failed to process approval');
  }
  return res.json();
}

export async function getMetrics(apiKey?: string): Promise<Metrics> {
  const res = await fetch(`${API_BASE}/api/metrics`, {
    headers: getHeaders(apiKey),
  });
  if (!res.ok) throw new Error(`Failed to load metrics: ${res.statusText}`);
  return res.json();
}

export async function getTools(apiKey?: string) {
  const res = await fetch(`${API_BASE}/api/tools`, {
    headers: getHeaders(apiKey),
  });
  if (!res.ok) throw new Error(`Failed to load tools: ${res.statusText}`);
  return res.json();
}
