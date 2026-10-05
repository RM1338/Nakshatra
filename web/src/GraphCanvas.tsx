import { useEffect, useRef, useState } from 'react';
import cytoscape, { type Core, type ElementDefinition } from 'cytoscape';
// @ts-expect-error: no type declarations ship with this layout
import coseBilkent from 'cytoscape-cose-bilkent';
import type { GraphOp } from './useRunStream';
import type { Ring } from './types';

cytoscape.use(coseBilkent);

export const RING_COLORS = ['#F0A33A', '#E8739A', '#4FC1B0', '#B7A2FF', '#C6D96B'];
const LAYOUT_EVERY_MS = 1500;
const LAYOUT_MAX_NODES = 2500; // above this, new nodes keep their seeded positions

// Focus view (default): a place appears only once two followed reviewers share it. Everything a single reviewer
// visited is noise for the question "do these accounts move together?", so it stays hidden unless asked for.
const style: cytoscape.StylesheetJson = [
  { selector: 'node', style: { 'border-width': 0, label: '', 'transition-property': 'opacity', 'transition-duration': 200 } },
  { selector: 'node.user', style: { shape: 'ellipse', width: 3, height: 3, 'background-color': '#7F8FC4', opacity: 0.4 } },
  { selector: 'node.user.followed', style: { width: 9, height: 9, 'background-color': '#AFC0F0', opacity: 1 } },
  { selector: 'node.place', style: { shape: 'round-rectangle', width: 'data(size)', height: 'data(size)', 'background-color': '#5E6A9C' } },
  { selector: 'node.place.shared', style: { 'background-color': '#C9D3F5' } },
  { selector: 'node.place.hub, node.place.ring', style: {
      label: 'data(short)', color: '#E6EBFA', 'font-size': 9,
      'font-family': 'Atkinson Hyperlegible, sans-serif', 'text-valign': 'bottom', 'text-margin-y': 3,
      'text-outline-color': '#141936', 'text-outline-width': 2 } },
  { selector: 'node.seed', style: {
      shape: 'round-rectangle', width: 26, height: 26, 'background-color': '#FFF4DA', label: 'data(short)',
      color: '#FFF4DA', 'font-family': 'Spectral, serif', 'font-size': 13, 'text-valign': 'bottom', 'text-margin-y': 6,
      'text-outline-color': '#141936', 'text-outline-width': 3 } },
  { selector: 'edge', style: { width: 0.8, 'line-color': '#55619A', opacity: 0.7, 'curve-style': 'haystack' } },
  { selector: 'edge.seedEdge', style: { 'line-color': '#3C4677', opacity: 0.3, width: 0.5 } },
  { selector: '.leaf', style: { display: 'none' } },
  { selector: '.ring', style: { 'background-color': 'data(ringColor)', 'line-color': 'data(ringColor)', opacity: 1, 'z-index': 10 } },
  { selector: 'edge.ring', style: { width: 1.8 } },
  { selector: 'node.ring.user', style: { width: 11, height: 11, label: 'data(badge)', color: '#141936', 'font-size': 7,
      'text-valign': 'center', 'text-margin-y': 0, 'font-weight': 'bold', 'text-outline-width': 0 } },
  { selector: '.dim', style: { opacity: 0.1 } },
  { selector: 'node.place.hoverable:active, node.place:selected', style: { 'border-width': 2, 'border-color': '#FFF4DA' } },
];

function placeSize(d_p: number | null | undefined) {
  return 4 + 2.5 * Math.log10((d_p ?? 50) + 1);
}

function short(title: string) {
  const t = title.split(/\s[|–-]\s/)[0];
  return t.length > 28 ? `${t.slice(0, 26)}…` : t;
}

interface Props {
  queue: React.MutableRefObject<GraphOp[]>;
  rings?: Ring[];               // final rings (result); reported ones get colours
  selectedRing?: number | null; // dims everything else
  onPlace?: (dataId: string) => void;
  label: string;                // accessible summary of what the graph shows
  followedTotal?: number;       // once the result is in: the authoritative count of followed reviewers
}

export default function GraphCanvas({ queue, rings, selectedRing, onPlace, label, followedTotal }: Props) {
  const host = useRef<HTMLDivElement>(null);
  const cyRef = useRef<Core | null>(null);
  const onPlaceRef = useRef(onPlace);
  onPlaceRef.current = onPlace;
  const [showAll, setShowAll] = useState(false);
  const showAllRef = useRef(showAll);
  const [counts, setCounts] = useState({ followed: 0, shared: 0 });
  const relayoutRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    const cy = cytoscape({ container: host.current, style, minZoom: 0.15, maxZoom: 4 });
    cyRef.current = cy;
    cy.on('tap', 'node.place', (e) => onPlaceRef.current?.(e.target.id()));
    let raf = 0;
    let lastLayout = 0;
    let dirty = false;
    let seedId: string | null = null;
    const visitors = new Map<string, number>(); // place id -> followed reviewers who reviewed it
    let followed = 0, shared = 0;

    const relayout = () => {
      const eles = showAllRef.current ? cy.elements() : cy.elements().filter((e) =>
        e.isNode() ? !e.hasClass('leaf') : !e.target().hasClass('leaf'));
      if (eles.nodes().length <= LAYOUT_MAX_NODES) {
        eles.layout({ name: 'cose-bilkent', randomize: false, animate: false, fit: true, padding: 30,
                      nodeRepulsion: 6000, idealEdgeLength: 55, numIter: 800, tile: false } as cytoscape.LayoutOptions).run();
      } else {
        cy.fit(eles, 30);
      }
    };

    const drain = (now: number) => {
      const ops = queue.current.splice(0, queue.current.length);
      if (ops.length) {
        cy.batch(() => {
          for (const op of ops) {
            if (op.t === 'node') {
              const d = op.d;
              if (cy.getElementById(d.id).nonempty()) continue;
              const isSeed = d.role === 'seed';
              const seedNode = seedId ? cy.getElementById(seedId) : null;
              const anchor = !isSeed && seedNode?.nonempty() ? seedNode.position() : { x: 0, y: 0 };
              if (isSeed) seedId = d.id;
              const r = isSeed ? 0 : 60 + Math.random() * 220;
              const a = Math.random() * Math.PI * 2;
              const el: ElementDefinition = {
                group: 'nodes',
                data: { id: d.id, label: d.label ?? '', short: short(d.label ?? ''), size: placeSize(d.d_p), role: d.role ?? '' },
                classes: [d.kind, isSeed ? 'seed' : '', d.kind === 'place' && !isSeed ? 'hoverable leaf' : ''].join(' '),
                position: { x: anchor.x + r * Math.cos(a), y: anchor.y + r * Math.sin(a) },
              };
              cy.add(el);
              dirty = true;
            } else if (op.t === 'edge') {
              const id = `${op.d.u}|${op.d.p}`;
              if (cy.getElementById(id).nonempty()) continue;
              const userNode = cy.getElementById(op.d.u);
              const placeNode = cy.getElementById(op.d.p);
              if (userNode.empty() || placeNode.empty()) continue;
              const toSeed = op.d.p === seedId;
              if (!toSeed) {
                // only reviewers sampled from this place get followed; others were discovered on a shared place's page
                if (userNode.data('role') === 'seed_reviewer' && !userNode.hasClass('followed')) {
                  userNode.addClass('followed'); followed += 1;
                }
                const n = (visitors.get(op.d.p) ?? 0) + 1;
                visitors.set(op.d.p, n);
                if (n === 1) {
                  const p = userNode.position();
                  placeNode.position({ x: p.x + (Math.random() - 0.5) * 80, y: p.y + (Math.random() - 0.5) * 80 });
                } else if (n === 2) {
                  placeNode.removeClass('leaf').addClass('shared');
                  shared += 1;
                } else if (n === 3) {
                  placeNode.addClass('hub');  // labelled: three or more followed reviewers went here
                }
              }
              cy.add({ group: 'edges', data: { id, source: op.d.u, target: op.d.p }, classes: toSeed ? 'seedEdge' : '' });
              dirty = true;
            } else {
              paintRings(cy, [{ members: op.d.members, places: op.d.places, color: RING_COLORS[0], badge: '1' }]);
            }
          }
        });
        setCounts({ followed, shared });
      }
      if (dirty && now - lastLayout > LAYOUT_EVERY_MS) {
        dirty = false;
        lastLayout = now;
        relayout();
      }
      raf = requestAnimationFrame(drain);
    };
    raf = requestAnimationFrame(drain);

    // The stage switches from the live layout to the report layout: keep the drawing fitted to its new box.
    const ro = new ResizeObserver(() => { cy.resize(); relayout(); });
    if (host.current) ro.observe(host.current);
    relayoutRef.current = relayout;
    return () => { ro.disconnect(); cancelAnimationFrame(raf); cy.destroy(); };
  }, [queue]);

  useEffect(() => {
    showAllRef.current = showAll;
    const cy = cyRef.current;
    if (!cy) return;
    cy.style().selector('.leaf').style('display', showAll ? 'element' : 'none').update();
    relayoutRef.current?.();
  }, [showAll]);

  // Final rings from the result: colour every reported ring; dim the rest when one is selected.
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy || !rings) return;
    const reported = rings.filter((r) => r.reported);
    paintRings(cy, reported.map((r, i) => ({
      members: r.stream_members, places: r.places.map((p) => p.data_id),
      color: RING_COLORS[i % RING_COLORS.length], badge: String(i + 1), idx: r.idx,
    })), selectedRing ?? null);
  }, [rings, selectedRing]);

  return (
    <div className="graph-wrap">
      <div ref={host} className="graph" role="img" aria-label={label} />
      <div className="legend" aria-hidden="true">
        <span><i className="lg-seed" /> this place</span>
        <span><i className="lg-user" /> reviewers we followed ({followedTotal ?? counts.followed})</span>
        <span><i className="lg-place" /> places two or more of them reviewed ({counts.shared})</span>
        {rings?.some((r) => r.reported) && <span><i className="lg-ring" /> coordinated group</span>}
      </div>
      <label className="show-all">
        <input type="checkbox" checked={showAll} onChange={(e) => setShowAll(e.target.checked)} />
        Show every place they reviewed
      </label>
      {counts.followed > 0 && counts.shared === 0 && !showAll && (
        <p className="graph-empty">None of the followed reviewers share a place yet: they look unconnected.</p>
      )}
    </div>
  );
}

function paintRings(cy: Core,
                    rings: { members: string[]; places: string[]; color: string; badge: string; idx?: number }[],
                    selected: number | null = null) {
  cy.batch(() => {
    cy.elements().removeClass('ring dim');
    for (const r of rings) {
      const ids = new Set([...r.members, ...r.places]);
      const nodes = cy.nodes().filter((n) => ids.has(n.id()));
      nodes.data({ ringColor: r.color, badge: r.badge }).addClass('ring').removeClass('leaf');
      nodes.connectedEdges().filter((e) => ids.has(e.source().id()) && ids.has(e.target().id()))
        .data('ringColor', r.color).addClass('ring');
    }
    if (selected !== null) {
      const keep = rings.find((r) => r.idx === selected);
      if (keep) {
        const ids = new Set([...keep.members, ...keep.places]);
        cy.nodes().filter((n) => !ids.has(n.id()) && !n.hasClass('seed')).addClass('dim');
        cy.edges().filter((e) => !(ids.has(e.source().id()) && ids.has(e.target().id()))).addClass('dim');
      }
    }
  });
}
