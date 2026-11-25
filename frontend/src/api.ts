import type { ExperimentRun, HealthResponse } from './types';

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => request<HealthResponse>('/api/health'),
  listRuns: () => request<ExperimentRun[]>('/api/runs'),
  createRun: (prompt: string, target_file?: string) =>
    request<ExperimentRun>('/api/runs', {
      method: 'POST',
      body: JSON.stringify({ prompt, target_file: target_file || null }),
    }),
  approveSetup: (runId: string, note = '') =>
    request<ExperimentRun>(`/api/runs/${runId}/approve-setup`, {
      method: 'POST',
      body: JSON.stringify({ note }),
    }),
  rejectRun: (runId: string, note = '') =>
    request<ExperimentRun>(`/api/runs/${runId}/reject`, {
      method: 'POST',
      body: JSON.stringify({ note }),
    }),
  simulateTraffic: (runId: string, sessions = 80, treatment_uplift_bias = 0.42) =>
    request<ExperimentRun>(`/api/runs/${runId}/simulate`, {
      method: 'POST',
      body: JSON.stringify({ sessions, treatment_uplift_bias }),
    }),
  approveRollout: (runId: string, winning_variant?: string, note = '') =>
    request<ExperimentRun>(`/api/runs/${runId}/approve-rollout`, {
      method: 'POST',
      body: JSON.stringify({ winning_variant: winning_variant || null, note }),
    }),
  demoSource: () => request<{ target_file: string; content: string }>('/api/demo-app/source'),
  updateConfig: (payload: Record<string, string>) =>
    request<{ saved: string[]; health: HealthResponse }>('/api/config', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
};
