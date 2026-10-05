import type { Health, LedgerPage, Problem, RunStatus, RunSummary } from './types';

const BASE = '/api/v1';

export class ApiError extends Error {
  constructor(public problem: Problem, public status: number, public runId: string | null = null) {
    super(problem.message);
  }
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(BASE + path, { headers: { 'Content-Type': 'application/json' }, ...init });
  const body = await r.json().catch(() => null);
  if (!r.ok) {
    const e = body?.error ?? { code: 'E_INTERNAL', message: `HTTP ${r.status}` };
    throw new ApiError({ code: e.code, message: e.message }, r.status, e.run_id ?? null);
  }
  return body as T;
}

export const api = {
  health: () => call<Health>('/health'),
  runs: () => call<RunSummary[]>('/runs?limit=50'),
  run: (id: string) => call<RunStatus>(`/runs/${id}`),
  cancel: (id: string) => call<RunStatus>(`/runs/${id}/cancel`, { method: 'POST' }),
  ledger: (id: string) => call<LedgerPage>(`/runs/${id}/ledger?limit=500`),
  create: (place: string, budget: number, offline: boolean) =>
    call<{ run_id: string }>('/runs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Idempotency-Key': crypto.randomUUID() },
      body: JSON.stringify({ place, budget, offline }),
    }),
};

// SRS-IN-1: a Maps URL or raw data_id carries 0x…:0x…; a place_id starts with ChIJ.
export function findPlaceId(s: string): string | null {
  const m = s.match(/0x[0-9a-f]+:0x[0-9a-f]+/i) ?? s.match(/\bChIJ[0-9A-Za-z_-]{10,}/);
  return m ? m[0] : null;
}
