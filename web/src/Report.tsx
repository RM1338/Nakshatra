import { useEffect, useState } from 'react';
import { RING_COLORS } from './GraphCanvas';
import { api } from './api';
import type { EvidencePlace, LedgerPage, Ring, RunStatus } from './types';

// ---------- S3 result ----------
type Result = NonNullable<RunStatus['result']>;
type Health = NonNullable<Result['health']>;
type Level = 'flag' | 'ok' | 'na';
const LIGHT_N = 15;

export function ResultPanel({ result, status, selectedRing, setSelectedRing, openPlace, openLedger, rerun, newRun }: {
  result: Result; status: RunStatus; selectedRing: number | null;
  setSelectedRing: (i: number | null) => void; openPlace: (id: string) => void; openLedger: () => void;
  rerun: (offline: boolean, extra?: number) => void; newRun: () => void;
}) {
  const reported = result.rings.filter((r) => r.reported);
  const others = result.rings.filter((r) => !r.reported);
  const [showOthers, setShowOthers] = useState(false);
  const cov = result.coverage;
  const h = result.health;
  const has = (f: string) => !!h?.flags.includes(f as never);
  const flags = [reported.length > 0, has('new_accounts') || has('experience_gap'), has('burst'), has('recent_gap')]
    .filter(Boolean).length;  // one per flagged card
  const thin = !h || h.n < LIGHT_N || cov.reviewers_expanded < 5;

  const head = reported.length
    ? { title: 'Coordinated reviewing found', sub: result.verdict ?? '' }
    : flags
      ? { title: `${flags} thing${flags > 1 ? 's' : ''} worth a closer look`,
          sub: 'No group of accounts moving together was found, but the recent reviews show patterns worth knowing before you trust the rating.' }
      : thin
        ? { title: 'Not enough data for a clear answer',
            sub: `This check read only ${h?.n ?? cov.reviewers_sampled} recent reviews. Run it again with a bigger budget.` }
        : { title: 'Nothing unusual found',
            sub: 'The reviewers we checked look like ordinary, unconnected people, and the recent reviews look normal.' };

  return (
    <div className="result">
      <header className={`headline ${flags ? 'is-flag' : ''}`}>
        <h1>{head.title}</h1>
        <p>{head.sub}</p>
        {cov.low_coverage && (
          <p className="badge-low" title="The search was still finding new connections when the budget ran out.">Low coverage</p>
        )}
      </header>

      <RatingStrip result={result} />

      {!h && (
        <p className="banner">
          This result was made before the review checks existed. Press <strong>Replay offline</strong> below (free) to add them.
        </p>
      )}

      <section className="findings" aria-label="Findings">
        <CrewFinding result={result} reported={reported}
                     onSelect={(idx) => setSelectedRing(selectedRing === idx ? null : idx)} />
        {h && <WhoFinding h={h} />}
        {h && <BurstFinding h={h} />}
        {h && <RecentFinding h={h} />}
      </section>

      {reported.length > 0 && (
        <section aria-label="Coordinated groups">
          <h2 className="section-title">The coordinated group{reported.length > 1 ? 's' : ''}</h2>
          {reported.map((r, i) => (
            <RingCard key={r.idx} ring={r} n={i + 1} color={RING_COLORS[i % RING_COLORS.length]}
                      selected={selectedRing === r.idx}
                      onSelect={() => setSelectedRing(selectedRing === r.idx ? null : r.idx)}
                      openPlace={openPlace} />
          ))}
        </section>
      )}

      {result.reviewers && result.reviewers.length > 0 && <ReviewerTable rows={result.reviewers} />}

      <WhatWeChecked result={result} budget={status.credits.budget} />
      <HowToRead />
      {others.length > 0 && (
        <div className="others">
          <button className="link" onClick={() => setShowOthers(!showOthers)} aria-expanded={showOthers}>
            {showOthers ? 'Hide' : 'Show'} {others.length} loose group{others.length > 1 ? 's' : ''} that chance could explain
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
        <ExportMenu runId={status.run_id} />
        <button onClick={openLedger}>Ledger</button>
        <button onClick={() => rerun(true)}>Replay offline</button>
        {status.credits.used > 0 && <button onClick={() => rerun(false, 40)}>Rerun with a bigger budget</button>}
        <button className="primary" onClick={newRun}>New investigation</button>
      </div>
    </div>
  );
}

function RatingStrip({ result }: { result: Result }) {
  const { rating, seed } = result;
  const h = result.health;
  const setAside = rating.set_aside ?? 0;
  const adjusted = useCountTo(rating.displayed, setAside ? rating.adjusted : null);
  const [lo, hi] = rating.ci;
  return (
    <section className="rating-strip" aria-label="Ratings">
      <Figure value={rating.displayed} label="Google rating"
              note={seed.d_p !== null ? `${seed.d_p.toLocaleString()} reviews` : ''} />
      {setAside > 0 ? (
        <Figure value={adjusted} strong label={`Without the ${setAside} coordinated account${setAside > 1 ? 's' : ''}`}
                note={lo !== null && hi !== null ? `likely ${lo.toFixed(1)}–${hi.toFixed(1)}` : ''}
                title="Newest reviews with the coordinated accounts' reviews set aside, pulled slightly toward similar places nearby; interval from 1,000 resamples." />
      ) : (
        <Figure value={h?.avg_recent ?? rating.sample_mean} label="Newest reviews"
                note={`average of ${h?.n ?? rating.n_sampled}`} />
      )}
      <Figure value={h?.rating_experienced ?? null} strong={!setAside} label="Experienced reviewers"
              note={h?.rating_experienced != null ? `${h.n_experienced} people with 10+ reviews` : 'too few in the sample'}
              title="Average from recent reviewers who have written 10 or more reviews anywhere. Long-standing accounts are the hardest to buy." />
    </section>
  );
}

function Figure({ value, label, note, strong, title }: {
  value: number | null; label: string; note: string; strong?: boolean; title?: string;
}) {
  return (
    <div className={`figure ${strong ? 'strong' : ''}`} title={title}>
      <span className="figure-num">{value !== null ? value.toFixed(1) : '–'}</span>
      <span className="figure-label">{label}</span>
      <span className="figure-note">{note}</span>
    </div>
  );
}

function Finding({ level, title, children }: { level: Level; title: string; children: React.ReactNode }) {
  const chip = { flag: 'Worth a look', ok: 'Looks normal', na: 'Not enough data' }[level];
  return (
    <article className={`finding ${level}`}>
      <header><h3>{title}</h3><span className="chip">{chip}</span></header>
      {children}
    </article>
  );
}

function CrewFinding({ result, reported, onSelect }: { result: Result; reported: Ring[]; onSelect: (idx: number) => void }) {
  const cov = result.coverage;
  if (reported.length) {
    const r = reported[0];
    return (
      <Finding level="flag" title="Accounts that move together">
        <p className="finding-big">{r.members.length} accounts share {r.places.length} unrelated places</p>
        <p>By chance, two of them would share about {fmtN(r.expected_overlap)} places; they share {fmtN(r.observed_overlap)}.
          Randomly shuffled data produced a group this tight in fewer than 1% of tries.</p>
        <button className="link" onClick={() => onSelect(r.idx)}>Highlight them on the map</button>
      </Finding>
    );
  }
  if (cov.reviewers_expanded < 5) {
    return (
      <Finding level="na" title="Accounts that move together">
        <p>Only {cov.reviewers_expanded} reviewers were followed, too few to tell.</p>
      </Finding>
    );
  }
  const m = cov.max_shared_places;
  return (
    <Finding level="ok" title="Accounts that move together">
      <p>We opened the review history of {cov.reviewers_expanded} reviewers. They don't keep reviewing the same places as each other
        {m === 0 ? <>: <strong>no two of them</strong> reviewed any of the same places</>
          : m !== undefined ? <>: the most any two had in common was <strong>{m} other place{m === 1 ? '' : 's'}</strong></> : ''}.</p>
    </Finding>
  );
}

const pct = (x: number | null) => (x === null ? '–' : `${Math.round(x * 100)}%`);

function WhoFinding({ h }: { h: Health }) {
  if (h.n_known < 10) {
    return <Finding level="na" title="Who wrote the recent reviews"><p>Too few recent reviews were read to tell ({h.n}).</p></Finding>;
  }
  const flagged = h.flags.includes('new_accounts') || h.flags.includes('experience_gap');
  return (
    <Finding level={flagged ? 'flag' : 'ok'} title="Who wrote the recent reviews">
      <p className="finding-big">{pct(h.new_share)} from brand-new accounts</p>
      <p>Of the newest {h.n} reviews, {h.n_new} come from accounts with 2 or fewer reviews ever
        {h.five_star_share_new !== null ? `; ${pct(h.five_star_share_new)} of those are 5 stars` : ''}
        {h.no_text_share_new !== null ? ` and ${pct(h.no_text_share_new)} have no written text` : ''}.</p>
      {h.rating_new !== null && h.rating_experienced !== null && (
        <p>Brand-new accounts give it <strong>{h.rating_new.toFixed(1)}</strong>; experienced reviewers give it{' '}
          <strong>{h.rating_experienced.toFixed(1)}</strong>.
          {h.flags.includes('experience_gap')
            ? ' When newcomers rate a place much higher than experienced reviewers, the newcomers’ reviews deserve a closer look.'
            : ''}</p>
      )}
    </Finding>
  );
}

const DAYM = new Intl.DateTimeFormat('en-IN', { day: 'numeric', month: 'short', year: 'numeric' });

function BurstFinding({ h }: { h: Health }) {
  const b = h.burst;
  if (h.n < 10) return <Finding level="na" title="Bursts of reviews"><p>Too few recent reviews were read to tell.</p></Finding>;
  if (b && h.flags.includes('burst')) {
    return (
      <Finding level="flag" title="Bursts of reviews">
        <p className="finding-big">{b.count} reviews in 3 days</p>
        <p>Between {DAYM.format(new Date(b.start * 1000))} and {DAYM.format(new Date(b.end * 1000))}: {b.five_star} of them
          5 stars, {b.new_accounts} from brand-new accounts. At this place's usual pace, about{' '}
          {b.expected < 1 ? 'one or fewer' : Math.round(b.expected)} would arrive in 3 days.</p>
      </Finding>
    );
  }
  return (
    <Finding level="ok" title="Bursts of reviews">
      <p>{b ? `The busiest 3 days had ${b.count} reviews with mixed ratings, which looks like an ordinary busy spell.`
             : 'Reviews arrive at a steady pace, with no sudden rush.'}</p>
    </Finding>
  );
}

function RecentFinding({ h }: { h: Health }) {
  if (h.n < 10 || h.avg_recent === null || h.displayed === null) {
    return <Finding level="na" title="Recent rating vs overall"><p>Too few recent reviews were read to tell.</p></Finding>;
  }
  const flagged = h.flags.includes('recent_gap');
  return (
    <Finding level={flagged ? 'flag' : 'ok'} title="Recent rating vs overall">
      <p className="finding-big">{h.avg_recent.toFixed(1)} recently, {h.displayed.toFixed(1)} overall</p>
      <p>{flagged
        ? `The newest ${h.n} reviews are noticeably ${h.avg_recent > h.displayed ? 'more' : 'less'} positive than the overall rating. That can have ordinary causes, such as a change in service, so read it together with the other checks.`
        : `The newest ${h.n} reviews are in line with the overall rating.`}</p>
    </Finding>
  );
}

function ReviewerTable({ rows }: { rows: NonNullable<Result['reviewers']> }) {
  const [all, setAll] = useState(false);
  const sorted = [...rows].sort((a, b) =>
    (a.ring === null ? 1 : 0) - (b.ring === null ? 1 : 0) || b.places_shared - a.places_shared);
  const shown = all ? sorted : sorted.slice(0, 8);
  return (
    <section className="reviewers" aria-label="Reviewers we followed">
      <h2 className="section-title">Reviewers we followed</h2>
      <p className="muted">Names are hidden. Shared places are ones that at least one other reviewer here also reviewed.</p>
      <table>
        <thead><tr><th scope="col">Reviewer</th><th scope="col">Reviews ever</th><th scope="col">Stars here</th>
          <th scope="col">When</th><th scope="col">Places shared with the others</th></tr></thead>
        <tbody>
          {shown.map((r) => (
            <tr key={r.member} className={r.ring !== null ? 'in-ring' : ''}>
              <td>{r.member}{r.ring !== null && <span className="ring-tag">group</span>}</td>
              <td>{r.reviews_total}</td>
              <td aria-label={r.rating_here !== null ? `${r.rating_here} stars` : 'not known'}>
                {r.rating_here !== null ? '★'.repeat(Math.round(r.rating_here)) : '–'}</td>
              <td>{r.t_here !== null ? DAYM.format(new Date(r.t_here * 1000)) : '–'}</td>
              <td>{r.places_shared}{r.most_with_one > 1 ? `, ${r.most_with_one} of them with the same person` : ''}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {rows.length > 8 && <button className="link" onClick={() => setAll(!all)}>{all ? 'Show fewer' : `Show all ${rows.length}`}</button>}
    </section>
  );
}

function WhatWeChecked({ result, budget }: { result: NonNullable<RunStatus['result']>; budget: number }) {
  const cov = result.coverage;
  const total = result.seed.d_p;
  // Two different reasons a check stops short: too small a budget, or the search found nothing forming and stopped
  // on purpose (it saves credits). Only the first one is a reason to rerun with more credits.
  const smallBudget = budget < 40 || (cov.low_coverage ?? false);
  const stoppedEarly = !smallBudget && cov.reviewers_expanded < 15;
  const m = cov.max_shared_places;
  return (
    <section className="checked" aria-label="What we checked">
      <h2>What we checked</h2>
      <p>
        Read {cov.reviewers_sampled.toLocaleString()} {total !== null ? `of ${total.toLocaleString()} ` : ''}reviews and
        opened the full review history of {cov.reviewers_expanded} reviewers, {cov.places.toLocaleString()} places in all.
      </p>
      {m !== undefined && (cov.pairs_compared ?? 0) > 0 && (
        <p>
          Comparing those reviewers two at a time ({cov.pairs_compared} pairs), the most any two had in common was{' '}
          <strong>{m} other place{m === 1 ? '' : 's'}</strong>.
          {m <= 2 ? ' That is what unconnected people look like.' : ''}
        </p>
      )}
      {smallBudget && (
        <p className="light">
          This was a light check. A budget of 60 or more follows more reviewers and gives a more reliable answer.
        </p>
      )}
      {stoppedEarly && (
        <p className="light">
          The search stopped after {cov.reviewers_expanded} reviewers because no connections were forming between them, which
          saves credits. Following more reviewers rarely changes that answer.
        </p>
      )}
    </section>
  );
}

function HowToRead() {
  return (
    <details className="how">
      <summary>How to read this</summary>
      <p>
        Review sellers reuse the same accounts for many clients, so their accounts keep turning up together at the same
        unrelated, little-known places. Nakshatra follows this place's reviewers to everything else they reviewed and
        looks for such a group.
      </p>
      <p>
        A group is reported only when randomly shuffled data almost never produces one as tight (under 1% of the time).
        It then shows the rating with that group's reviews set aside. &ldquo;No coordination detected&rdquo; means the
        reviewers it followed look like unconnected people. It is a statistical check, not a verdict about anyone.
      </p>
    </details>
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
      {ring.notes?.map((n) => <p key={n} className="ring-note">{n}</p>)}
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
          {ring.guards && (
            <>
              <dt title="Variance of the star ratings these accounts gave the shared places. Crews tend to give uniform stars.">Rating variance</dt>
              <dd>{ring.guards.rating_variance ?? '–'}</dd>
              <dt title="Median distance between pairs of shared places.">Places spread</dt>
              <dd>{ring.guards.spread_km === null ? '–' : `${ring.guards.spread_km.toFixed(1)} km`}</dd>
            </>
          )}
          <dt>Accounts</dt>
          <dd>{ring.members.join(', ')}</dd>
        </dl>
      )}
      <p className="explain muted">{ring.explanation}</p>
    </article>
  );
}

// ---------- export with the reporting guardrail (UF §5, Flow B) ----------
function ExportMenu({ runId }: { runId: string }) {
  const [open, setOpen] = useState(false);
  const [acked, setAcked] = useState(() => {
    try { return sessionStorage.getItem('nk-dossier-ack') === '1'; } catch { return false; }
  });
  const ack = () => {
    try { sessionStorage.setItem('nk-dossier-ack', '1'); } catch { /* private mode: ask again next time */ }
    setAcked(true);
  };
  return (
    <>
      <button onClick={() => setOpen(true)} aria-haspopup="dialog">Export dossier</button>
      {open && (
        <div className="drawer" role="dialog" aria-modal="true" aria-labelledby="export-title">
          <button className="drawer-close" onClick={() => setOpen(false)} autoFocus>Close</button>
          <h2 id="export-title">Export the evidence</h2>
          <p>The dossier lists every coordinated group with each account, the shared places and dates, the statistics,
             and every SerpApi search behind them.</p>
          <p className="banner">This file contains Google Maps contributor IDs. Use it for reporting to Google or a
             consumer authority, not for publication.</p>
          {!acked ? (
            <button className="primary" onClick={ack}>I understand</button>
          ) : (
            <div className="toolbar">
              <a className="button primary" href={`/api/v1/runs/${runId}/dossier?format=md`} download>Download Markdown</a>
              <a className="button" href={`/api/v1/runs/${runId}/dossier?format=pdf`} download>Download PDF</a>
            </div>
          )}
        </div>
      )}
    </>
  );
}

// ---------- O1 place drawer ----------
export function PlaceDrawer({ place, ring, color, onClose }: { place: EvidencePlace; ring: Ring; color: string; onClose: () => void }) {
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

export function LedgerDrawer({ runId, onClose }: { runId: string; onClose: () => void }) {
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
