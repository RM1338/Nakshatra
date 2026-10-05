import { useCallback, useEffect, useMemo, useState } from 'react';
import GraphCanvas, { RING_COLORS } from './GraphCanvas';
import { api, ApiError, findPlaceId } from './api';
import { useRunStream } from './useRunStream';
import type { EvidencePlace, Health, LedgerPage, Phase, Problem, Ring, RunStatus, RunSummary } from './types';

// ---------- routing: "/" and "/runs/:id" (UF §3) ----------
type Route = { name: 'home'; banner?: string } | { name: 'run'; id: string };

function readRoute(): Route {
  const m = location.pathname.match(/^\/runs\/(r_[0-9a-f]{10})$/);
  return m ? { name: 'run', id: m[1] } : { name: 'home', banner: history.state?.banner };
}

export default function App() {
  const [route, setRoute] = useState<Route>(readRoute);
  useEffect(() => {
    const on = () => setRoute(readRoute());
    window.addEventListener('popstate', on);
    return () => window.removeEventListener('popstate', on);
  }, []);
  const go = useCallback((path: string, banner?: string) => {
    history.pushState(banner ? { banner } : null, '', path);
    setRoute(readRoute());
  }, []);
  return route.name === 'run'
    ? <RunView key={route.id} runId={route.id} go={go} />
    : <Home banner={route.banner} go={go} />;
}

// ---------- copy (UF §6, final unless marked) ----------
function problemCopy(p: Problem): string {
  switch (p.code) {
    case 'E_BAD_PLACE': return "That doesn't look like a Google Maps place link. Copy the link from the place's Share button.";
    case 'E_RUN_ACTIVE': return 'An investigation is already running.';
    case 'E_AUTH': return 'No SerpApi key found. You can replay cached runs offline, or add a key to .env.';
    case 'E_TOO_FEW_REVIEWS': return `${p.message}, which is too few to test for coordination.`;
    case 'E_CACHE_MISS': return "This place isn't in the offline cache. Add a SerpApi key to run it live.";
    case 'E_QUOTA': return 'Your SerpApi credits ran out. Showing what was found so far.';
    case 'E_UPSTREAM': return "Couldn't load this place from SerpApi. Try again in a minute.";
    case 'E_BUDGET': return 'Choose a budget between 20 and 200 credits.';
    default: return `Something went wrong on the local server (${p.code}). Try again.`;
  }
}

const PHASES: { key: Phase[]; label: string }[] = [
  { key: ['created', 'resolving'], label: 'Looking up the place' },
  { key: ['sampling'], label: 'Reading recent reviews' },
  { key: ['expanding'], label: 'Following reviewers' },
  { key: ['refining'], label: 'Checking places they share' },
  { key: ['mining', 'reporting'], label: 'Checking whether this could be chance' },
];
const ORDER: Phase[] = ['created', 'resolving', 'sampling', 'expanding', 'refining', 'mining', 'reporting', 'done'];

// ---------- S1 Home ----------
function Home({ banner, go }: { banner?: string; go: (p: string, b?: string) => void }) {
  const [text, setText] = useState('');
  const [budget, setBudget] = useState(60);
  const [offline, setOffline] = useState(false);
  const [health, setHealth] = useState<Health | null>(null);
  const [recent, setRecent] = useState<RunSummary[]>([]);
  const [problem, setProblem] = useState<Problem | null>(null);
  const [activeRun, setActiveRun] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const id = findPlaceId(text);
  // UF §3: offer cache-only runs when there is no key, or when this place was crawled before (0 credits).
  const cached = !!id && recent.some((r) => r.state === 'done' && r.seed_data_id?.toLowerCase() === id.toLowerCase());
  useEffect(() => { if (cached) setOffline(true); }, [cached]);

  useEffect(() => {
    api.health().then((h) => { setHealth(h); setOffline(!h.api_key_present || h.offline_forced); }).catch(() => {});
    api.runs().then(setRecent).catch(() => {});
  }, []);

  const start = async (e?: React.FormEvent) => {
    e?.preventDefault();
    if (!id) { setProblem({ code: 'E_BAD_PLACE', message: '' }); return; }
    setBusy(true);
    setProblem(null);
    try {
      const r = await api.create(text, budget, offline);
      go(`/runs/${r.run_id}`);
    } catch (err) {
      if (err instanceof ApiError) {
        setProblem(err.problem);
        setActiveRun(err.runId);
      }
    } finally {
      setBusy(false);
    }
  };

  const keyMissing = health && !health.api_key_present;
  return (
    <main className="home">
      <div className="home-sky" aria-hidden="true"><Constellation /></div>
      <section className="home-panel">
        <h1>Are these reviewers connected?</h1>
        <p className="lede">
          Paste a Google Maps place. Nakshatra follows its reviewers to their other reviews, looks for groups that
          keep reviewing the same unrelated places together, and tests whether that could be chance.
        </p>
        {(banner || keyMissing || health?.offline_forced) && (
          <p className="banner" role="status">
            {banner ?? (health?.offline_forced ? 'Offline mode: replaying cached runs, 0 credits.'
              : 'No SerpApi key found. You can replay cached runs offline, or add a key to .env.')}
          </p>
        )}
        <form onSubmit={start} className="investigate">
          <label htmlFor="place" className="sr-only">Google Maps link or place ID</label>
          <input id="place" autoFocus value={text} onChange={(e) => { setText(e.target.value); setProblem(null); }}
                 placeholder="Paste a Google Maps link" autoComplete="off" spellCheck={false}
                 aria-describedby="place-help" aria-invalid={problem?.code === 'E_BAD_PLACE'} />
          <p id="place-help" className={`helper ${problem ? 'is-error' : id ? 'is-ok' : ''}`} aria-live="polite">
            {problem ? problemCopy(problem) : id ? 'Found a place ID. Ready to investigate.' : ' '}
            {problem?.code === 'E_RUN_ACTIVE' && activeRun &&
              <> <a href={`/runs/${activeRun}`} onClick={(e) => { e.preventDefault(); go(`/runs/${activeRun}`); }}>View it</a></>}
          </p>
          <div className="controls">
            <label className="budget">
              <span>Search budget: <strong>{budget}</strong> SerpApi credits</span>
              <input type="range" min={20} max={200} step={5} value={budget}
                     onChange={(e) => setBudget(Number(e.target.value))} />
            </label>
            {(keyMissing || health?.offline_forced || cached) && (
              <label className="toggle">
                <input type="checkbox" checked={offline} disabled={!!keyMissing || !!health?.offline_forced}
                       onChange={(e) => setOffline(e.target.checked)} />
                {cached && !keyMissing ? 'Replay from cache (0 credits). Untick to fetch fresh data.' : 'Use cached data only (0 credits)'}
              </label>
            )}
            <button type="submit" className="primary" disabled={busy}>Investigate</button>
          </div>
        </form>
        {recent.length > 0 && (
          <nav className="recent" aria-label="Recent investigations">
            <h2>Recent investigations</h2>
            <ul>
              {recent.slice(0, 8).map((r) => (
                <li key={r.run_id}>
                  <a href={`/runs/${r.run_id}`} onClick={(e) => { e.preventDefault(); go(`/runs/${r.run_id}`); }}>
                    {r.seed_title ?? 'Unresolved place'}
                  </a>
                  <span className="muted">
                    {r.state === 'done' ? (r.rings_reported ? `${r.rings_reported} coordinated group${r.rings_reported > 1 ? 's' : ''}` : 'No coordination detected')
                      : r.state === 'failed' ? 'Stopped' : 'Running'}
                  </span>
                </li>
              ))}
            </ul>
          </nav>
        )}
      </section>
    </main>
  );
}

function Constellation() {
  // A quiet star field with one marigold figure: what the product looks for, drawn once.
  const stars = useMemo(() => {
    let h = 2166136261; // deterministic scatter (FNV-style), same sky on every load
    const rnd = () => { h = Math.imul(h ^ (h >>> 15), 2246822507) ^ Math.imul(h ^ (h >>> 13), 3266489909); h >>>= 0; return h / 4294967296; };
    return Array.from({ length: 140 }, () => ({ x: rnd() * 100, y: rnd() * 100, r: 0.08 + rnd() * rnd() * 0.35 }));
  }, []);
  const fig = [[62, 30], [70, 24], [78, 33], [74, 44], [64, 41], [70, 24]];
  return (
    <svg viewBox="0 0 100 100" preserveAspectRatio="xMidYMid slice">
      {stars.map((s, i) => <circle key={i} cx={s.x} cy={s.y} r={s.r} fill="#AFC0F0" opacity={0.5} />)}
      <polyline points={fig.map((p) => p.join(',')).join(' ')} fill="none" stroke="#F0A33A" strokeWidth="0.25" opacity="0.8" />
      {fig.slice(0, 5).map(([x, y], i) => <circle key={i} cx={x} cy={y} r={0.7} fill="#F0A33A" />)}
    </svg>
  );
}

// ---------- S2 live + S3 result ----------
function RunView({ runId, go }: { runId: string; go: (p: string, b?: string) => void }) {
  const { state: s, graphQueue } = useRunStream(runId);
  const [status, setStatus] = useState<RunStatus | null>(null);
  const [seedTitle, setSeedTitle] = useState<string>('');
  const [now, setNow] = useState(Date.now() / 1000);
  const [selectedRing, setSelectedRing] = useState<number | null>(null);
  const [place, setPlace] = useState<string | null>(null);
  const [ledgerOpen, setLedgerOpen] = useState(false);

  useEffect(() => { api.run(runId).then(setStatus).catch(() => go('/', 'That investigation was not found.')); }, [runId, go]);
  useEffect(() => {
    if (s.terminal) api.run(runId).then(setStatus).catch(() => {});
  }, [s.terminal, runId]);
  useEffect(() => {
    if (s.terminal) return;
    const t = window.setInterval(() => setNow(Date.now() / 1000), 1000);
    return () => window.clearInterval(t);
  }, [s.terminal]);
  useEffect(() => {
    if (status?.result?.seed.title) setSeedTitle(status.result.seed.title);
  }, [status]);
  useEffect(() => {  // seed-level failures return home with the explanation (UF §2)
    if (s.terminal === 'error' && s.error && ['E_TOO_FEW_REVIEWS', 'E_CACHE_MISS', 'E_AUTH', 'E_BAD_PLACE'].includes(s.error.code)) {
      go('/', problemCopy(s.error));
    }
  }, [s.terminal, s.error, go]);

  const result = s.terminal === 'done' ? status?.result ?? null : null;
  const started = status?.started_at ?? s.firstTs ?? now;
  const ended = status?.ended_at ?? (s.terminal ? now : null);
  const elapsed = Math.max(0, Math.round((ended ?? now) - started));
  const budget = s.budget || status?.credits.budget || 0;
  const reported = result?.rings.filter((r) => r.reported) ?? [];
  const evidence = useMemo(() => {
    const m = new Map<string, { ring: Ring; place: EvidencePlace; color: string }>();
    reported.forEach((r, i) => r.evidence?.forEach((p) => m.set(p.data_id, { ring: r, place: p, color: RING_COLORS[i % RING_COLORS.length] })));
    return m;
  }, [reported]);

  useEffect(() => {
    const esc = (e: KeyboardEvent) => { if (e.key === 'Escape') { setPlace(null); setLedgerOpen(false); } };
    window.addEventListener('keydown', esc);
    return () => window.removeEventListener('keydown', esc);
  }, []);

  const rerun = async (offline: boolean, extra = 0) => {
    if (!result) return;
    try {
      const r = await api.create(result.seed.data_id, Math.min(200, budget + extra), offline);
      go(`/runs/${r.run_id}`);
    } catch (err) {
      if (err instanceof ApiError) go('/', problemCopy(err.problem));
    }
  };

  const graphLabel = result
    ? `Reviewer graph: ${result.coverage.reviewers_expanded} reviewers followed across ${result.coverage.places} places; ${reported.length} coordinated group${reported.length === 1 ? '' : 's'} highlighted.`
    : `Reviewer graph being built: ${s.reviewers} reviewers and ${s.places} places so far.`;

  return (
    <main className="run">
      <header className="topbar">
        <a href="/" className="brand" onClick={(e) => { e.preventDefault(); go('/'); }}>Nakshatra</a>
        <span className="seed-name">{s.seedTitle || seedTitle || ' '}</span>
        <span className={`phase-pill ${s.terminal ?? ''}`} aria-live="polite">
          {s.terminal === 'done' ? 'Done' : s.terminal === 'error' ? 'Stopped' : PHASES.find((p) => p.key.includes(s.phase))?.label}
        </span>
        <CreditBar used={s.used} cached={s.cached} budget={budget} offline={!!status && status.credits.used === 0 && s.cached > 0}
                   onOpen={() => setLedgerOpen(true)} />
        <span className="elapsed" title="Elapsed time">{Math.floor(elapsed / 60)}:{String(elapsed % 60).padStart(2, '0')}</span>
      </header>

      <div className="stage">
        <GraphCanvas queue={graphQueue} rings={result?.rings} selectedRing={selectedRing}
                     onPlace={(id) => evidence.has(id) && setPlace(id)} label={graphLabel} />
        {s.reconnecting && <p className="reconnecting" role="status">Reconnecting…</p>}

        <aside className="panel" aria-label={result ? 'Result' : 'Progress'}>
          {!result && !s.error && (
            <LivePanel s={s} />
          )}
          {s.error && !result && (
            <div className="notice" role="alert">
              <p>{problemCopy(s.error)}</p>
              <button className="primary" onClick={() => go('/')}>New investigation</button>
            </div>
          )}
          {result && status && (
            <ResultPanel result={result} status={status} selectedRing={selectedRing} setSelectedRing={setSelectedRing}
                         openPlace={setPlace} openLedger={() => setLedgerOpen(true)}
                         rerun={rerun} newRun={() => go('/')} />
          )}
        </aside>
      </div>

      {place && evidence.has(place) && <PlaceDrawer {...evidence.get(place)!} onClose={() => setPlace(null)} />}
      {ledgerOpen && <LedgerDrawer runId={runId} onClose={() => setLedgerOpen(false)} />}
    </main>
  );
}

function CreditBar({ used, cached, budget, offline, onOpen }: { used: number; cached: number; budget: number; offline: boolean; onOpen: () => void }) {
  const pct = budget ? Math.min(100, ((used + cached) / budget) * 100) : 0;
  return (
    <button className="creditbar" onClick={onOpen} title="Open the credit ledger: every SerpApi request this run made">
      <span className="track" aria-hidden="true"><span className="fill" style={{ width: `${pct}%` }} /></span>
      <span>
        {offline ? `${cached} replayed from cache` : <>{used} of {budget} credits{cached ? `, ${cached} from cache` : ''}</>}
      </span>
    </button>
  );
}

function LivePanel({ s }: { s: ReturnType<typeof useRunStream>['state'] }) {
  const at = ORDER.indexOf(s.phase);
  return (
    <div className="live">
      <ol className="steps">
        {PHASES.map((p) => {
          const idx = Math.max(...p.key.map((k) => ORDER.indexOf(k)));
          const first = Math.min(...p.key.map((k) => ORDER.indexOf(k)));
          const state = p.key.includes(s.phase) ? 'now' : at > idx ? 'done' : at >= first ? 'now' : 'todo';
          return <li key={p.label} className={state} aria-current={state === 'now' ? 'step' : undefined}>{p.label}</li>;
        })}
      </ol>
      <section className="best-ring" aria-live="polite">
        <h2>Best group so far</h2>
        {s.ring ? (
          <>
            <p className="best-ring-line">{s.ring.members.length} accounts share {s.ring.places.length} places</p>
            <Sparkline values={s.ringHistory} />
          </>
        ) : (
          <p className="muted">No group yet. {s.reviewers} reviewers and {s.places} places so far.</p>
        )}
      </section>
      <ul className="ticker" aria-label="Recent activity">
        {s.ticker.map((t, i) => <li key={`${i}-${t}`}>{t}</li>)}
      </ul>
    </div>
  );
}

function Sparkline({ values }: { values: number[] }) {
  if (values.length < 2) return null;
  const max = Math.max(...values), w = 160, h = 28;
  const pts = values.map((v, i) => `${(i / (values.length - 1)) * w},${h - (v / max) * (h - 4) - 2}`).join(' ');
  return <svg className="spark" width={w} height={h} aria-hidden="true"><polyline points={pts} fill="none" stroke="#F0A33A" strokeWidth="1.5" /></svg>;
}

// ---------- S3 result ----------
function ResultPanel({ result, status, selectedRing, setSelectedRing, openPlace, openLedger, rerun, newRun }: {
  result: NonNullable<RunStatus['result']>; status: RunStatus; selectedRing: number | null;
  setSelectedRing: (i: number | null) => void; openPlace: (id: string) => void; openLedger: () => void;
  rerun: (offline: boolean, extra?: number) => void; newRun: () => void;
}) {
  const reported = result.rings.filter((r) => r.reported);
  const others = result.rings.filter((r) => !r.reported);
  const [showOthers, setShowOthers] = useState(false);
  const cov = result.coverage;
  return (
    <div className="result">
      <RatingCard rating={result.rating} />
      <p className="verdict">{result.verdict ?? result.no_coordination_message}</p>
      {cov.low_coverage && (
        <p className="badge-low" title="The search was still finding new connections when the budget ran out.">Low coverage</p>
      )}
      {reported.length > 0 && (
        <section aria-label="Coordinated groups">
          {reported.map((r, i) => (
            <RingCard key={r.idx} ring={r} n={i + 1} color={RING_COLORS[i % RING_COLORS.length]}
                      selected={selectedRing === r.idx} onSelect={() => setSelectedRing(selectedRing === r.idx ? null : r.idx)}
                      openPlace={openPlace} />
          ))}
        </section>
      )}
      <p className="coverage muted">
        Checked {cov.reviewers_expanded} reviewers' histories across {cov.places.toLocaleString()} places,
        from {cov.reviewers_sampled} recent reviews.
      </p>
      {others.length > 0 && (
        <div className="others">
          <button className="link" onClick={() => setShowOthers(!showOthers)} aria-expanded={showOthers}>
            {showOthers ? 'Hide' : 'Show'} {others.length} group{others.length > 1 ? 's' : ''} that chance could explain
          </button>
          {showOthers && (
            <ul>
              {others.map((r) => (
                <li key={r.idx}>{r.members.length} accounts, {r.places.length} places; permutation p = {fmtP(r.pval)}</li>
              ))}
            </ul>
          )}
        </div>
      )}
      <div className="toolbar">
        <button onClick={openLedger}>Ledger</button>
        <button onClick={() => rerun(true)}>Replay offline</button>
        {status.credits.used > 0 && <button onClick={() => rerun(false, 40)}>Rerun with a bigger budget</button>}
        <button className="primary" onClick={newRun}>New investigation</button>
      </div>
    </div>
  );
}

function RatingCard({ rating }: { rating: NonNullable<RunStatus['result']>['rating'] }) {
  const target = rating.adjusted;
  const shown = useCountTo(rating.displayed, target);
  const [lo, hi] = rating.ci;
  const x = (v: number) => `${((v - 1) / 4) * 100}%`;
  return (
    <section className="rating-card" aria-label="Rating">
      <div className="rating-pair">
        <div>
          <span className="rating-num">{rating.displayed?.toFixed(1) ?? '–'}</span>
          <span className="rating-cap">shown on Google</span>
        </div>
        <div title="Recent rating with coordinated accounts' reviews set aside, pulled slightly toward similar places nearby (κ = 5); interval from 1,000 resamples.">
          <span className="rating-num adjusted">{shown?.toFixed(1) ?? '–'}</span>
          <span className="rating-cap">recent rating, adjusted</span>
        </div>
      </div>
      {lo !== null && hi !== null && target !== null && (
        <div className="scale" aria-label={`Adjusted ${target.toFixed(1)}, likely between ${lo.toFixed(1)} and ${hi.toFixed(1)}`}>
          <span className="scale-range" style={{ left: x(lo), width: `calc(${x(hi)} - ${x(lo)})` }} />
          <span className="scale-dot" style={{ left: x(target) }} />
          {rating.displayed !== null && <span className="scale-shown" style={{ left: x(rating.displayed) }} />}
          <span className="scale-ends" aria-hidden="true"><span>1</span><span>5</span></span>
        </div>
      )}
      <p className="rating-note muted">
        Estimate from the newest {rating.n_sampled} reviews{lo !== null && hi !== null ? `, likely between ${lo.toFixed(1)} and ${hi.toFixed(1)}` : ''}.
      </p>
    </section>
  );
}

function useCountTo(from: number | null, to: number | null) {
  const [v, setV] = useState(to);
  useEffect(() => {
    if (from === null || to === null || Math.abs(from - to) < 0.05 || matchMedia('(prefers-reduced-motion: reduce)').matches) {
      setV(to);
      return;
    }
    let raf = 0;
    const t0 = performance.now();
    const step = (t: number) => {
      const k = Math.min(1, (t - t0) / 600);
      setV(from + (to - from) * (1 - (1 - k) ** 3));
      if (k < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [from, to]);
  return v;
}

function RingCard({ ring, n, color, selected, onSelect, openPlace }: {
  ring: Ring; n: number; color: string; selected: boolean; onSelect: () => void; openPlace: (id: string) => void;
}) {
  const [details, setDetails] = useState(false);
  return (
    <article className={`ring-card ${selected ? 'selected' : ''}`} style={{ '--ring': color } as React.CSSProperties}>
      <button className="ring-head" onClick={onSelect} aria-pressed={selected}>
        <span className="ring-badge" aria-hidden="true">{n}</span>
        <span>{ring.members.length} accounts share {ring.places.length} places unrelated to this business</span>
      </button>
      <p className="chance">
        <span title="Average number of places two of these accounts would share if every review were rewired at random, keeping each account's and each place's number of reviews.">
          Expected by chance: {fmtN(ring.expected_overlap)}</span>
        <span title="Mean number of places each pair of these accounts actually shares.">Observed: {fmtN(ring.observed_overlap)}</span>
      </p>
      <ul className="ring-places">
        {ring.places.map((p) => (
          <li key={p.data_id}>
            <button className="link" onClick={() => openPlace(p.data_id)}>{p.title}</button>
            <span className="muted"> {p.d_p !== null ? `${p.d_p.toLocaleString()} reviews` : 'review count unknown'}</span>
          </li>
        ))}
      </ul>
      <button className="link details-toggle" onClick={() => setDetails(!details)} aria-expanded={details}>
        {details ? 'Hide details' : 'Details'}
      </button>
      {details && (
        <dl className="details">
          <dt title="Share of 200+ randomly rewired versions of this crawl (each account and place keeps its number of reviews) where the same search found an equally dense group.">Permutation p</dt>
          <dd>{fmtP(ring.pval)}</dd>
          <dt title="City model: two accounts pick places in proportion to their review counts; median over pairs.">City model</dt>
          <dd>{ring.poisson_expected !== undefined ? `expected ${fmtN(ring.poisson_expected)}, p = ${ring.pair_pval !== undefined ? fmtP(ring.pair_pval) : '–'}` : '–'}</dd>
          <dt title="Popularity-weighted edges per node; reviews of obscure places count more.">Density</dt>
          <dd>{ring.density.toFixed(2)}</dd>
          <dt title="Share of shared places where most of these accounts posted within 14 days of each other.">Posted together</dt>
          <dd>{ring.lockstep_ratio === null ? 'Timing not resolvable (dates too coarse)' : `${Math.round(ring.lockstep_ratio * 100)}% of places`}</dd>
          <dt>Accounts</dt>
          <dd>{ring.members.join(', ')}</dd>
        </dl>
      )}
      <p className="explain muted">{ring.explanation}</p>
    </article>
  );
}

// ---------- O1 place drawer ----------
function PlaceDrawer({ place, ring, color, onClose }: { place: EvidencePlace; ring: Ring; color: string; onClose: () => void }) {
  const exact = place.reviews.filter((r) => r.exact).map((r) => r.t_lo!) ;
  const spanDays = exact.length > 1 ? Math.round((Math.max(...exact) - Math.min(...exact)) / 86400) : null;
  return (
    <div className="drawer" role="dialog" aria-modal="true" aria-labelledby="drawer-title">
      <button className="drawer-close" onClick={onClose} autoFocus>Close</button>
      <h2 id="drawer-title" style={{ borderColor: color }}>{place.title}</h2>
      <p className="muted">{place.d_p !== null ? `${place.d_p.toLocaleString()} people have ever reviewed this place.` : 'Review count unknown.'}</p>
      <p className="why">
        {place.reviews.length} of the {ring.members.length} accounts in this group reviewed it
        {spanDays !== null && place.reviews.every((r) => r.exact) ? `, all within ${Math.max(1, spanDays)} days` : ''}.
        {place.lockstep ? ' Most of them posted within two weeks of each other.' : ''}
      </p>
      <table>
        <thead><tr><th scope="col">Account</th><th scope="col">Stars</th><th scope="col">When</th></tr></thead>
        <tbody>
          {place.reviews.map((r) => (
            <tr key={r.member}>
              <td>{r.member}</td>
              <td aria-label={`${r.rating} stars`}>{'★'.repeat(Math.round(r.rating))}</td>
              <td>{fmtWhen(r.t_lo, r.t_hi, r.exact)} <span className={`when-badge ${r.exact ? 'exact' : 'approx'}`}>{r.exact ? 'exact' : 'approx.'}</span></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ---------- O2 ledger drawer ----------
const ENGINE: Record<string, string> = {
  google_maps: 'Place lookup or area search',
  google_maps_reviews: 'Place reviews',
  google_maps_contributor_reviews: 'Reviewer history',
};

function LedgerDrawer({ runId, onClose }: { runId: string; onClose: () => void }) {
  const [page, setPage] = useState<LedgerPage | null>(null);
  useEffect(() => { api.ledger(runId).then(setPage).catch(() => {}); }, [runId]);
  return (
    <div className="drawer wide" role="dialog" aria-modal="true" aria-labelledby="ledger-title">
      <button className="drawer-close" onClick={onClose} autoFocus>Close</button>
      <h2 id="ledger-title">Credit ledger</h2>
      {page && (
        <>
          <p>
            {page.totals.billed} billed, {page.totals.cached} from cache{page.totals.failed ? `, ${page.totals.failed} failed` : ''}.
            {' '}By step: {Object.entries(page.totals.by_pool).map(([k, v]) => `${{ sample: 'reading reviews', expand: 'following reviewers', refine: 'checking shared places' }[k] ?? k} ${v}`).join(', ')}.
          </p>
          <table>
            <thead><tr><th scope="col">SerpApi engine</th><th scope="col">Cost</th><th scope="col">Time</th><th scope="col">Search ID</th></tr></thead>
            <tbody>
              {page.items.map((i) => (
                <tr key={i.id} className={i.ok ? '' : 'failed'}>
                  <td>{ENGINE[i.engine] ?? i.engine}</td>
                  <td>{i.cached ? 'cache' : i.billed ? '1 credit' : 'not billed'}</td>
                  <td>{i.cached ? '–' : `${(i.latency_ms / 1000).toFixed(1)} s`}</td>
                  <td className="sid">{i.search_id ?? '–'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}

// ---------- formatting ----------
function fmtN(x: number) { return x >= 10 ? x.toFixed(0) : x >= 1 ? x.toFixed(1) : x.toFixed(2); }
function fmtP(p: number) { return p >= 0.001 ? p.toFixed(3) : p.toExponential(1); }
const MONTH = new Intl.DateTimeFormat('en-IN', { month: 'short', year: 'numeric' });
const DAYF = new Intl.DateTimeFormat('en-IN', { day: 'numeric', month: 'short', year: 'numeric' });
function fmtWhen(lo: number | null, hi: number | null, exact: boolean) {
  if (lo === null || hi === null) return 'date unknown';
  if (exact) return DAYF.format(new Date(lo * 1000));
  const a = MONTH.format(new Date(lo * 1000)), b = MONTH.format(new Date(hi * 1000));
  return a === b ? a : `${a} – ${b}`;
}
