// Mirrors API Contract §3–§5 (snake_case kept on the wire).
export type Phase =
  | 'created' | 'resolving' | 'sampling' | 'expanding' | 'refining'
  | 'mining' | 'reporting' | 'done' | 'failed' | 'cancelled';

export interface NodeEv { id: string; kind: 'user' | 'place'; label?: string; d_p?: number | null; role?: string }
export interface EdgeEv { u: string; p: string; rating: number; t_lo: number | null; t_hi: number | null; exact: boolean }
export interface RingEv { ring_idx: number; members: string[]; places: string[]; density: number }
export interface Problem { code: string; message: string }

export interface Place { data_id: string; title: string; d_p: number | null }
export interface EvidenceReview { member: string; rating: number; t_lo: number | null; t_hi: number | null; exact: boolean }
export interface EvidencePlace extends Place { lockstep: boolean; reviews: EvidenceReview[] }
export interface Ring {
  idx: number; members: string[]; stream_members: string[]; places: Place[];
  density: number; expected_overlap: number; observed_overlap: number;
  pval: number; pair_pval?: number; poisson_expected?: number; lockstep_ratio: number | null; reported: boolean; explanation: string;
  evidence?: EvidencePlace[];
  guards?: { rating_variance: number | null; spread_km: number | null; brand_token: string | null };
  notes?: string[];
}
export interface Result {
  seed: { data_id: string; title: string; rating: number | null; d_p: number | null };
  coverage: { reviewers_sampled: number; reviewers_expanded: number; places: number; edges: number; low_coverage?: boolean };
  rings: Ring[];
  rating: { displayed: number | null; adjusted: number | null; ci: [number | null, number | null];
            sample_mean: number | null; n_sampled: number; set_aside?: number };
  verdict?: string; no_coordination_message: string | null; config_hash: string;
}
export interface RunStatus {
  run_id: string; state: Phase; started_at: number; ended_at: number | null;
  credits: { budget: number; used: number; cached: number };
  error: Problem | null; result: Result | null; partial: Result | null;
}
export interface LedgerItem { id: number; engine: string; pool: string | null; cached: boolean; billed: boolean;
  ok: boolean; latency_ms: number; ts: number; search_id: string | null }
export interface LedgerPage { run_id: string; items: LedgerItem[]; next: number | null;
  totals: { billed: number; cached: number; failed: number; by_pool: Record<string, number> } }
export interface Health { status: string; api_key_present: boolean; offline_forced: boolean; active_run: string | null }
export interface RunSummary { run_id: string; state: Phase; seed_title: string | null; seed_data_id: string | null; started_at: number;
  credits_used: number; rings_reported: number }
export interface PlaceCandidate { data_id: string; title: string; type: string | null; rating: number | null;
  d_p: number | null; address: string | null; eligible: boolean }
