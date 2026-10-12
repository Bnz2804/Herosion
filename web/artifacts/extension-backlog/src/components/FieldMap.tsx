import type { FieldCandidate } from '@workspace/api-client-react';

type Origin = { lat: number; lon: number };
type Geometry = { coordinates?: number[][][] } | null | undefined;

/**
 * Tap-to-select map of candidate fields. Pure SVG, no map tiles (works offline, tiny).
 * Coordinates are converted to METRES around the plot so the drawing uses small, well-behaved numbers:
 * a viewBox spanning ~0.003 degrees renders blank on some mobile browsers.
 */
export function FieldMap({ origin, current, candidates, selected, onSelect }: {
  origin: Origin; current?: Geometry | Record<string, unknown>; candidates: FieldCandidate[]; selected: string | null; onSelect: (id: string) => void;
}) {
  const kx = Math.cos((origin.lat * Math.PI) / 180) * 111_320;
  const ky = 110_574;
  const toM = (lon: number, lat: number): [number, number] => [(lon - origin.lon) * kx, -(lat - origin.lat) * ky];
  const ring = (g: unknown): [number, number][] => ((g as Geometry)?.coordinates?.[0] ?? []).map(([lon, lat]) => toM(lon, lat));
  const rings = candidates.map(c => ({ c, pts: ring(c.geometry) }));
  const cur = current ? ring(current) : [];
  const all: [number, number][] = [...rings.flatMap(r => r.pts), ...cur, [0, 0]];
  const xs = all.map(p => p[0]);
  const ys = all.map(p => p[1]);
  const span = Math.max(Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys), 60);
  const pad = span * 0.12;
  const x0 = Math.min(...xs) - pad;
  const y0 = Math.min(...ys) - pad;
  const w = Math.max(...xs) - Math.min(...xs) + 2 * pad;
  const h = Math.max(...ys) - Math.min(...ys) + 2 * pad;
  const unit = Math.max(w, h) / 160;               // 1 "pixel" in drawing units
  const pts = (p: [number, number][]) => p.map(([x, y]) => `${x.toFixed(2)},${y.toFixed(2)}`).join(' ');
  const centre = (p: [number, number][]) => [p.reduce((a, q) => a + q[0], 0) / p.length, p.reduce((a, q) => a + q[1], 0) / p.length];
  const bar = [25, 50, 100, 200].find(m => m >= w * 0.18) ?? 200;   // scale bar length in metres

  return (
    <svg viewBox={`${x0.toFixed(2)} ${y0.toFixed(2)} ${w.toFixed(2)} ${h.toFixed(2)}`} width="100%" height="224"
      className="block w-full rounded-lg border border-border" role="img" preserveAspectRatio="xMidYMid meet"
      aria-label="Candidate fields around the plot. Tap a numbered field to select it.">
      <rect x={x0} y={y0} width={w} height={h} fill="#eef1e6" />
      {cur.length > 0 && <polygon points={pts(cur)} fill="none" stroke="#765a22" strokeWidth={unit * 1.5} strokeDasharray={`${unit * 5} ${unit * 3}`} />}
      {rings.map(({ c, pts: p }, i) => {
        const on = selected === c.candidateId;
        const [cx, cy] = centre(p);
        return (
          <g key={c.candidateId} onClick={() => onSelect(c.candidateId)} style={{ cursor: 'pointer' }}>
            <polygon points={pts(p)} fill={on ? '#315840' : '#d9b36a'} fillOpacity={on ? 0.8 : 0.55} stroke={on ? '#1d3a28' : '#765a22'} strokeWidth={unit * 2} />
            <circle cx={cx} cy={cy} r={unit * 6.5} fill="#fff" fillOpacity={0.85} />
            <text x={cx} y={cy} fontSize={unit * 8.5} fontWeight={700} textAnchor="middle" dominantBaseline="central" fill="#1d1d1d" style={{ pointerEvents: 'none' }}>{i + 1}</text>
          </g>
        );
      })}
      <circle cx={0} cy={0} r={unit * 6} fill="#a85143" stroke="#fff" strokeWidth={unit * 1.5} />
      <g transform={`translate(${x0 + pad * 0.5} ${y0 + h - pad * 0.5})`}>
        <line x1={0} y1={0} x2={bar} y2={0} stroke="#1d1d1d" strokeWidth={unit * 2} />
        <text x={0} y={-unit * 4} fontSize={unit * 10} fill="#1d1d1d">{bar} m</text>
      </g>
    </svg>
  );
}
