// src/api/index.ts
// API wrappers and SSE hook for the Universal Maintenance Agent backend.

export const API_BASE = '';  // proxied through Vite to localhost:8000

// ── Types ─────────────────────────────────────────────────────────────────────

export interface RunRequest {
  url: string;
  provider: 'gemini' | 'groq' | 'ollama' | 'auto';
  skip_sandbox: boolean;
  dependency?: string;
}

export interface RunCreated {
  run_id: string;
  status: string;
  started_at: number;
}

export interface AgentEvent {
  type: string;
  ts: number;
  phase?: string;
  agent?: string;
  status?: 'running' | 'done' | 'skipped' | 'warning' | 'error';
  message?: string;
  data?: Record<string, unknown>;
}

export interface Capsule {
  maintenance_problem_identified: string;
  relevant_dependency_or_repo_details: Record<string, unknown>;
  risk_indicators: string[];
  usage_locations: string[];
  ai_generated_analysis_or_recommendations: string;
  proposed_changes_or_maintenance_approach: string;
  suggested_tests_or_verification_steps: string[];
  recommended_patches: Array<{ file?: string; description?: string; unified_diff?: string }>;
  cov_log: string;
  executed_test_results: {
    command: string;
    exit_code: number;
    success: boolean;
    attempts: number;
    rolled_back: boolean;
    stdout_tail: string;
    stderr_tail: string;
    reflection_count: number;
  };
  compatibility_or_maintenance_gaps: string[];
  unresolved_concerns_and_limitations: string[];
  _meta: {
    generated_at: string;
    backend_used: string;
    schema_version: string;
  };
}

// ── REST calls ────────────────────────────────────────────────────────────────

export async function createRun(req: RunRequest): Promise<RunCreated> {
  const res = await fetch(`${API_BASE}/runs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  });
  if (!res.ok) throw new Error(`Failed to create run: ${res.statusText}`);
  return res.json();
}

export async function getCapsule(runId: string): Promise<Capsule> {
  const res = await fetch(`${API_BASE}/runs/${runId}/capsule`);
  if (!res.ok) throw new Error(`Capsule not ready: ${res.status}`);
  const data = await res.json();
  if (!data || data.detail || !data.maintenance_problem_identified) {
    throw new Error(data?.detail || 'Capsule not ready');
  }
  return data;
}

export async function getRunStatus(runId: string): Promise<{
  status: string; capsule_ready: boolean; started_at: number;
}> {
  const res = await fetch(`${API_BASE}/runs/${runId}/status`);
  if (!res.ok) throw new Error(`Status error: ${res.status}`);
  return res.json();
}

export function getExportUrl(runId: string, format: 'html' | 'json'): string {
  if (format === 'html') return `${API_BASE}/runs/${runId}/export?format=html`;
  return `${API_BASE}/runs/${runId}/capsule`;
}

// ── GitHub public API preview ─────────────────────────────────────────────────

export interface RepoMeta {
  name: string;
  description: string;
  language: string;
  stargazers_count: number;
  updated_at: string;
  full_name: string;
}

export async function fetchRepoMeta(url: string): Promise<RepoMeta | null> {
  try {
    const match = url.match(/github\.com\/([^/]+\/[^/]+)/);
    if (!match) return null;
    const slug = match[1].replace(/\.git$/, '');
    const res = await fetch(`https://api.github.com/repos/${slug}`);
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

// ── SSE Hook (custom EventSource) ────────────────────────────────────────────

export function subscribeToRun(
  runId: string,
  onEvent: (e: AgentEvent) => void,
  onDone: () => void,
): () => void {
  const es = new EventSource(`${API_BASE}/runs/${runId}/events`);

  es.onmessage = (ev) => {
    try {
      const parsed: AgentEvent = JSON.parse(ev.data);
      onEvent(parsed);
      if (parsed.type === 'done' || parsed.type === 'completed') {
        onDone();
        es.close();
      }
    } catch {
      // ignore malformed frames
    }
  };

  es.onerror = () => {
    onDone();
    es.close();
  };

  return () => es.close();
}
