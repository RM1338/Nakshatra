import { useEffect, useRef, useState } from 'react';
import type { EdgeEv, NodeEv, Phase, Problem, RingEv } from './types';

export type GraphOp = { t: 'node'; d: NodeEv } | { t: 'edge'; d: EdgeEv } | { t: 'ring'; d: RingEv };

export interface StreamState {
  phase: Phase;
  used: number;
  budget: number;
  cached: number;
  reviewers: number;
  places: number;
  ring: RingEv | null;
  ringHistory: number[]; // best-ring size after each update, for the sparkline
  ticker: string[];
  warnings: number;
  error: Problem | null;
  terminal: 'done' | 'cancelled' | 'error' | null;
  firstTs: number | null;
  reconnecting: boolean;
  seedTitle: string;
}

const initial: StreamState = {
  phase: 'created', used: 0, budget: 0, cached: 0, reviewers: 0, places: 0, ring: null, ringHistory: [],
  ticker: [], warnings: 0, error: null, terminal: null, firstTs: null, reconnecting: false, seedTitle: '',
};

const TYPES = ['phase', 'credit', 'node', 'edge', 'ring_update', 'warning', 'done', 'cancelled', 'error'] as const;

/** SSE stream with server-side replay (API §4). Graph ops are queued for the canvas; UI state updates once per frame. */
export function useRunStream(runId: string | undefined) {
  const [state, setState] = useState<StreamState>(initial);
  const graphQueue = useRef<GraphOp[]>([]);

  useEffect(() => {
    if (!runId) return;
    setState(initial);
    graphQueue.current = [];
    let s: StreamState = { ...initial };
    let frame = 0;
    let sinceCredit = new Map<string, number>(); // edges per reviewer since the last credit, for the ticker
    const flush = () => { frame = 0; setState(s); };
    const schedule = () => { if (!frame) frame = requestAnimationFrame(flush); };
    const say = (line: string) => { s = { ...s, ticker: [line, ...s.ticker].slice(0, 3) }; };

    const es = new EventSource(`/api/v1/runs/${runId}/events`);
    let stale: number | undefined;
    es.onopen = () => { window.clearTimeout(stale); s = { ...s, reconnecting: false }; schedule(); };
    es.onerror = () => {
      if (s.terminal) return;
      window.clearTimeout(stale);
      stale = window.setTimeout(() => { s = { ...s, reconnecting: true }; schedule(); }, 10_000);
    };

    for (const t of TYPES) {
      es.addEventListener(t, (e: MessageEvent) => {
        const d = JSON.parse(e.data);
        switch (t) {
          case 'phase':
            s = { ...s, phase: d.phase, firstTs: s.firstTs ?? d.ts };
            break;
          case 'credit': {
            const prevUsed = s.used + s.cached;
            s = { ...s, used: d.used, budget: d.budget, cached: d.cached };
            if (s.phase === 'expanding' || s.phase === 'refining') {
              let best = 0;
              sinceCredit.forEach((n) => { best = Math.max(best, n); });
              if (best > 0 && d.used + d.cached > prevUsed) say(`Followed a reviewer: ${best} other ${best === 1 ? 'place' : 'places'}`);
            }
            sinceCredit = new Map();
            break;
          }
          case 'node':
            graphQueue.current.push({ t: 'node', d });
            if (d.role === 'seed') s = { ...s, seedTitle: d.label ?? '' };
            if (d.kind === 'user') {
              s = { ...s, reviewers: s.reviewers + 1 };
              if (s.phase === 'sampling' && s.reviewers % 8 === 0) say(`Read ${s.reviewers} recent reviews`);
            } else {
              s = { ...s, places: s.places + 1 };
            }
            break;
          case 'edge':
            graphQueue.current.push({ t: 'edge', d });
            sinceCredit.set(d.u, (sinceCredit.get(d.u) ?? 0) + 1);
            break;
          case 'ring_update':
            graphQueue.current.push({ t: 'ring', d });
            s = { ...s, ring: d, ringHistory: [...s.ringHistory, d.members.length] };
            say(`${d.members.length} accounts share ${d.places.length} places`);
            break;
          case 'warning':
            s = { ...s, warnings: s.warnings + 1 };
            if (d.code === 'E_UPSTREAM') say("Skipped one reviewer (SerpApi didn't respond). Continuing.");
            break;
          case 'done':
          case 'cancelled':
            s = { ...s, terminal: t };
            es.close();
            break;
          case 'error':
            s = { ...s, terminal: 'error', error: d, phase: 'failed' };
            es.close();
            break;
        }
        schedule();
      });
    }
    return () => { es.close(); cancelAnimationFrame(frame); window.clearTimeout(stale); };
  }, [runId]);

  return { state, graphQueue };
}
