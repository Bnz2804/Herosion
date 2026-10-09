import { type FormEvent, type ReactNode, useEffect, useMemo, useState } from 'react';
import { QueryClient, QueryClientProvider, useQueryClient } from '@tanstack/react-query';
import { Link, Route, Switch, useLocation } from 'wouter';
import {
  Activity, ArrowRight, Check, CheckCircle2, ChevronDown,
  CircleAlert, ClipboardList, CloudRain, FileCheck2, FileText, Filter, Fingerprint,
  MapPin, Menu, Microscope, Plus, RefreshCw, Search, ShieldCheck, Sprout,
} from 'lucide-react';
import {
  getGetAdvisoriesQueryKey, getGetAgentStatusQueryKey, getGetAuditEventsQueryKey, getGetClustersQueryKey, getGetClusterEvidenceQueryKey,
  getGetClusterPlotsQueryKey, getGetOverviewQueryKey, getHealthCheckQueryKey, useApproveAdvisory,
  useCreateEvidenceRun, useCreateManualAdvisory, useGetAdvisories, useGetAgentStatus,
  useGetAuditEvents, useGetClusterEvidence, useGetClusterPlots, useGetClusters,
  useGetOverview, useHealthCheck, useSubmitAgentDrafts, useGetPlotFieldCandidates, useMatchPlotField, getGetPlotFieldCandidatesQueryKey,
} from '@workspace/api-client-react';
import type { Advisory, EvidenceItem, EvidenceRun, Plot, FieldCandidate } from '@workspace/api-client-react';
import { Toaster } from '@/components/ui/toaster';
import { TooltipProvider } from '@/components/ui/tooltip';
import { ErrorBoundary } from '@/components/error-boundary';
import './index.css';

const queryClient = new QueryClient();

function formatDate(value?: string | null) {
  if (!value) return 'Not recorded';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat('en', { day: 'numeric', month: 'short', year: 'numeric' }).format(date);
}

function formatTime(value?: string | null) {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat('en', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }).format(date);
}

function Skeleton({ rows = 3 }: { rows?: number }) {
  return <div className="space-y-3" aria-label="Loading records">{Array.from({ length: rows }, (_, i) => <div key={i} className="h-16 animate-pulse rounded-xl bg-muted/80" />)}</div>;
}

function QueryError({ retry }: { retry: () => void }) {
  return <div className="flex items-start gap-3 rounded-xl border border-[#bd796c]/30 bg-[#bd796c]/[.08] p-4 text-sm"><CircleAlert className="mt-0.5 h-4 w-4 shrink-0 text-[#a85143]" /><div className="flex-1"><p className="font-semibold">This record could not be loaded.</p><p className="mt-1 text-muted-foreground">The workbench has not substituted example data.</p><button onClick={retry} className="mt-3 inline-flex items-center gap-2 font-semibold text-primary" data-testid="button-retry"><RefreshCw size={14} />Try again</button></div></div>;
}

function DataTag() {
  return <span className="inline-flex items-center gap-1.5 rounded-full border border-[#c9a761]/40 bg-[#e9d8a9]/30 px-2.5 py-1 font-data text-[10px] font-medium uppercase tracking-[.08em] text-[#705826]"><span className="h-1.5 w-1.5 rounded-full bg-[#b28a3a]" />Local test data</span>;
}

function StatusPill({ children, tone = 'neutral' }: { children: ReactNode; tone?: 'neutral' | 'warning' | 'good' }) {
  const style = tone === 'warning' ? 'bg-[#f3e5c7] text-[#765a22]' : tone === 'good' ? 'bg-[#dce9df] text-[#315840]' : 'bg-muted text-muted-foreground';
  return <span className={`inline-flex items-center rounded-full px-2.5 py-1 text-[11px] font-semibold ${style}`}>{children}</span>;
}

function Shell({ children, active }: { children: ReactNode; active: string }) {
  const [menuOpen, setMenuOpen] = useState(false);
  const nav = [
    { href: '/', label: 'Overview', icon: Activity },
    { href: '/investigate', label: 'Investigate', icon: Microscope },
    { href: '/advisories', label: 'Advisories', icon: FileCheck2 },
    { href: '/audit', label: 'Audit trail', icon: ClipboardList },
  ];
  return <div className="grain min-h-[100dvh] bg-background">
    <aside className={`fixed inset-y-0 left-0 z-40 flex w-[248px] flex-col border-r border-sidebar-border bg-sidebar text-sidebar-foreground transition-transform duration-200 md:translate-x-0 ${menuOpen ? 'translate-x-0' : '-translate-x-full'}`}>
      <div className="border-b border-sidebar-border px-6 pb-6 pt-7">
        <div className="flex items-center gap-3">
          <div className="grid h-10 w-10 place-items-center rounded-xl bg-sidebar-primary text-sidebar-primary-foreground"><Sprout size={21} strokeWidth={1.8} /></div>
          <div><p className="font-data text-[9px] uppercase tracking-[.2em] text-sidebar-foreground/55">Benin · Fieldwork</p><p className="mt-1 font-display text-[19px] leading-none">Herosion</p></div>
        </div>
        <div className="mt-7 rounded-lg border border-sidebar-border bg-[#10271f]/50 px-3 py-3">
          <div className="flex items-center gap-2 text-[11px] font-semibold text-[#e0c780]"><span className="h-1.5 w-1.5 rounded-full bg-[#d2b35e]" />Prototype environment</div>
          <p className="mt-1.5 text-[10px] leading-relaxed text-sidebar-foreground/55">All records are local test data. Not a live field feed.</p>
        </div>
      </div>
      <nav className="flex-1 px-3 py-5">
        <p className="px-3 pb-3 font-data text-[9px] uppercase tracking-[.17em] text-sidebar-foreground/45">Workspace</p>
        <div className="space-y-1">{nav.map(item => {
          const Icon = item.icon;
          const selected = active === item.href;
          return <Link key={item.href} href={item.href} onClick={() => setMenuOpen(false)} data-testid={`link-nav-${item.label.toLowerCase().replace(' ', '-')}`} className={`group flex items-center gap-3 rounded-lg px-3 py-2.5 text-[13px] transition-colors ${selected ? 'bg-sidebar-accent text-sidebar-accent-foreground' : 'text-sidebar-foreground/65 hover:bg-sidebar-accent/70 hover:text-sidebar-foreground'}`}>
            <Icon size={16} strokeWidth={1.8} /><span className="flex-1">{item.label}</span>{selected && <span className="h-1.5 w-1.5 rounded-full bg-sidebar-primary" />}
          </Link>;
        })}</div>
      </nav>
      <div className="border-t border-sidebar-border p-4">
        <div className="flex items-center gap-3 rounded-lg px-2 py-2">
          <div className="grid h-8 w-8 place-items-center rounded-full border border-sidebar-border bg-sidebar-accent font-data text-[10px]">EO</div>
          <div className="min-w-0 flex-1"><p className="truncate text-xs font-semibold">Officer workspace</p><p className="mt-0.5 font-data text-[9px] text-sidebar-foreground/50">Self-attested identity</p></div>
          <Fingerprint size={15} className="text-sidebar-foreground/45" />
        </div>
      </div>
    </aside>
    {menuOpen && <button aria-label="Close navigation" onClick={() => setMenuOpen(false)} className="fixed inset-0 z-30 bg-[#13221c]/30 md:hidden" />}
    <div className="min-h-[100dvh] md:pl-[248px]">
      <header className="sticky top-0 z-20 flex h-[62px] items-center justify-between border-b border-border/80 bg-background/95 px-4 backdrop-blur md:px-9">
        <div className="flex items-center gap-3"><button className="grid h-9 w-9 place-items-center rounded-lg hover:bg-muted md:hidden" onClick={() => setMenuOpen(!menuOpen)} aria-label="Toggle navigation"><Menu size={18} /></button><div className="hidden items-center gap-2 text-xs text-muted-foreground sm:flex"><span>Field operations</span><span className="text-border">/</span><span className="font-medium capitalize text-foreground">{active === '/' ? 'Overview' : active.slice(1)}</span></div><div className="sm:hidden font-data text-[10px] uppercase tracking-widest text-muted-foreground">Herosion</div></div>
        <div className="flex items-center gap-2"><span className="hidden font-data text-[10px] text-muted-foreground sm:inline">BENIN · WORKBENCH</span><span className="h-4 w-px bg-border" /><DataTag /></div>
      </header>
      <main className="mx-auto max-w-[1440px] px-4 pb-14 pt-7 md:px-9 md:pt-9">{children}</main>
    </div>
  </div>;
}

function SectionHeading({ eyebrow, title, description, action }: { eyebrow: string; title: string; description?: string; action?: ReactNode }) {
  return <div className="mb-7 flex flex-col justify-between gap-4 sm:flex-row sm:items-end"><div><p className="font-data text-[10px] uppercase tracking-[.18em] text-[#8c7041]">{eyebrow}</p><h1 className="mt-2 font-display text-[34px] leading-[1.05] tracking-[-.025em] sm:text-[42px]">{title}</h1>{description && <p className="mt-2 max-w-2xl text-sm leading-relaxed text-muted-foreground">{description}</p>}</div>{action}</div>;
}

function AgentNotice({ status }: { status?: { modelConfigured: boolean; modelName?: string | null; agentServiceReachable: boolean; advisoryGenerationAvailable: boolean; weatherLive: boolean; identityMode: string; farmerDeliveryEnabled: boolean } }) {
  return <section className="mb-6 overflow-hidden rounded-xl border border-[#cbbd9c] bg-[#f0e8d3]/80">
    <div className="flex flex-col gap-4 px-5 py-4 lg:flex-row lg:items-center lg:justify-between">
      <div className="flex gap-3"><div className="mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-[#e1d2ad] text-[#6e592f]"><ShieldCheck size={17} /></div><div><p className="text-sm font-bold">Human control is active</p><p className="mt-1 max-w-2xl text-xs leading-relaxed text-[#655d4b]">The agent only drafts, and only from tool results. Every draft needs approval by a different named officer. No farmer delivery is available.</p></div></div>
      <div className="grid grid-cols-2 gap-x-5 gap-y-2 border-t border-[#d7c9a9] pt-3 text-[10px] sm:grid-cols-4 lg:border-l lg:border-t-0 lg:pl-5 lg:pt-0">
        <Capability label="Model" value={status?.modelConfigured ? `Configured · ${status.modelName ?? 'unnamed'}` : status && !status.agentServiceReachable ? 'Agent service offline' : 'Not configured'} active={!!status?.modelConfigured} />
        <Capability label="Live weather" value={status?.weatherLive ? 'Connected' : 'Unavailable'} active={!!status?.weatherLive} />
        <Capability label="Identity" value={status?.identityMode === 'self_attested_prototype' ? 'Self-attested' : status?.identityMode || 'Unknown'} active={false} />
        <Capability label="Delivery" value={status?.farmerDeliveryEnabled ? 'Enabled' : 'Disabled'} active={!!status?.farmerDeliveryEnabled} />
      </div>
    </div>
    {status && (!status.agentServiceReachable || !status.modelConfigured || !status.weatherLive || status.identityMode === 'self_attested_prototype' || !status.farmerDeliveryEnabled) && <div className="border-t border-[#d7c9a9] px-5 py-2.5 font-data text-[9px] uppercase tracking-[.08em] text-[#746543]">Limits · synthetic test data, no authenticated identity, no live weather, no farmer messaging</div>}
  </section>;
}


const REC_LABEL: Record<string, string> = {
  delay_planting: 'Consider delaying', proceed_with_planting: 'May proceed', already_planted_monitor: 'Planted · monitor',
  insufficient_evidence: 'Insufficient evidence', not_applicable: 'Not applicable',
};
const SUBMITTABLE = new Set(['delay_planting', 'proceed_with_planting', 'already_planted_monitor']);

function AgentRunPanel({ run, selection, onToggle, submitter, setSubmitter, pending, message, onSubmit }: {
  run: EvidenceRun; selection: string[]; onToggle: (id: string) => void; submitter: string; setSubmitter: (v: string) => void;
  pending: boolean; message: string; onSubmit: () => void;
}) {
  const recs = run.householdRecommendations ?? [];
  const evidenceById = new Map(run.evidence.map(e => [e.evidenceId, e]));
  return <div className="mt-4 space-y-3 rounded-lg border border-[#cfc3a5] bg-[#f7f2e5] p-3" data-testid="status-evidence-run">
    <div className="flex items-center justify-between gap-2"><StatusPill tone="good">{run.status}</StatusPill><span className="font-data text-[9px] text-muted-foreground">{run.runId}</span></div>
    <p className="font-data text-[9px] uppercase tracking-[.08em] text-muted-foreground">Agent-driven · {run.modelName ?? 'model'} · {run.toolCalls.length} tool calls chosen by the agent</p>
    {run.conclusion && <div><p className="font-data text-[9px] uppercase tracking-[.12em] text-muted-foreground">Draft conclusion</p><p className="mt-1 text-xs leading-relaxed">{run.conclusion}</p></div>}
    {recs.length > 0 && <div><p className="font-data text-[9px] uppercase tracking-[.12em] text-muted-foreground">Household recommendations (drafts)</p>
      <div className="mt-1.5 divide-y divide-[#d8cba9] rounded-md border border-[#d8cba9]">{recs.map(r => <label key={r.householdId} className="flex gap-2 px-2.5 py-2">
        <input type="checkbox" disabled={!SUBMITTABLE.has(r.recommendation)} checked={selection.includes(r.householdId)} onChange={() => onToggle(r.householdId)} className="mt-0.5 accent-[#315840]" data-testid={`checkbox-rec-${r.householdId}`} />
        <span className="min-w-0 flex-1"><span className="flex flex-wrap items-center gap-2"><span className="text-[11px] font-semibold">{r.householdId}</span><StatusPill tone={r.recommendation === 'delay_planting' ? 'warning' : r.recommendation === 'proceed_with_planting' ? 'good' : 'neutral'}>{REC_LABEL[r.recommendation] ?? r.recommendation}</StatusPill></span>
          <span className="mt-1 block text-[10px] leading-relaxed text-muted-foreground">{r.rationale}</span>
          {r.missingData.length > 0 && <span className="mt-1 block text-[9px] text-[#a85143]">Missing data: {r.missingData.join(', ')}</span>}
          <span className="mt-1 block font-data text-[8px] text-muted-foreground">Cites {r.evidenceIds.filter(id => evidenceById.has(id)).length} evidence record(s)</span></span></label>)}</div>
      <div className="mt-2 space-y-2"><input value={submitter} onChange={e => setSubmitter(e.target.value)} minLength={2} maxLength={120} placeholder="Your full name (submitting officer)" className="h-9 w-full rounded-lg border border-input bg-background px-3 text-xs outline-none focus:border-primary" data-testid="input-submitting-officer" />
        <button type="button" onClick={onSubmit} disabled={pending || selection.length === 0 || submitter.trim().length < 2} className="flex w-full items-center justify-center gap-2 rounded-lg bg-[#315840] px-4 py-2.5 text-xs font-semibold text-white hover:opacity-90 disabled:opacity-50" data-testid="button-submit-agent-drafts">{pending ? 'Submitting' : <><FileCheck2 size={14} />Submit {selection.length || ''} selected as drafts for second-officer approval</>}</button>
        </div></div>}
    <div><p className="font-data text-[9px] uppercase tracking-[.12em] text-muted-foreground">Tool trace</p>
      <ol className="mt-1.5 space-y-2">{run.toolCalls.map((call, i) => <li key={`${call.auditCallId ?? call.toolName}-${i}`} className="border-l-2 border-[#cfc3a5] pl-2.5">
        {call.decision && <p className="text-[10px] italic leading-relaxed text-[#6d6553]">Agent: {call.decision}</p>}
        <p className="mt-0.5 font-data text-[9px] text-foreground">{call.toolName} · {call.status} · {call.resultCount} records{call.auditCallId ? ` · ${call.auditCallId}` : ''}</p>
        {call.arguments && <p className="font-data text-[8px] text-muted-foreground">{call.arguments}</p>}
        {call.summary && <p className="mt-0.5 text-[10px] leading-relaxed text-muted-foreground">{call.summary}</p>}</li>)}</ol></div>
    {run.limitations.map((limitation, i) => <p className="text-[10px] leading-relaxed text-[#765a35]" key={i}>{limitation}</p>)}
    <details><summary className="cursor-pointer text-[10px] font-semibold">{run.evidence.length} cited source records</summary>{run.evidence.map(item => <div key={item.evidenceId} className="mt-2 border-t border-[#d8cba9] pt-2"><p className="text-[10px] font-semibold">{item.label}</p><p className="mt-1 text-[9px] text-muted-foreground">{item.sourceName} · {item.sourceRecordId}</p></div>)}</details>
  </div>;
}

const CONF_TONE: Record<string, 'good' | 'warning' | 'neutral'> = { high: 'good', medium: 'good', low: 'warning', very_low: 'warning' };
const CONF_TEXT: Record<string, string> = { high: 'Location: high', medium: 'Location: medium', low: 'Location: low', very_low: 'Location: village only' };
const LEVEL_TEXT: Record<string, string> = { cadastral: 'Registered boundary', officer_surveyed: 'Officer GPS survey', officer_matched: 'Satellite field, officer-confirmed', satellite_candidate: 'Satellite field, not confirmed', declared: 'Declared only' };

function PlotCards({ plots, onConfirm }: { plots: Plot[]; onConfirm: (plotId: string) => void }) {
  return <ul className="divide-y divide-border" data-testid="list-plots">{plots.map(plot => {
    const protectedPlot = plot.verificationLevel === 'cadastral' || plot.verificationLevel === 'officer_surveyed';
    const mismatch = plot.areaCheck?.startsWith('mismatch');
    return <li key={plot.plotId} className="px-4 py-3.5" data-testid={`row-plot-${plot.plotId}`}>
      <div className="flex items-start justify-between gap-3"><div className="min-w-0"><p className="truncate text-sm font-semibold">{plot.householdName}</p><p className="font-data text-[9px] text-muted-foreground">{plot.plotId} · {plot.crop} · {plot.areaHa} ha · {plot.variety}</p></div><StatusPill>{plot.plantingStatus}</StatusPill></div>
      <div className="mt-2 flex flex-wrap items-center gap-1.5"><StatusPill tone={CONF_TONE[plot.locationConfidence ?? 'very_low']}>{CONF_TEXT[plot.locationConfidence ?? 'very_low']}</StatusPill><span className="text-[10px] text-muted-foreground">{LEVEL_TEXT[plot.verificationLevel ?? 'declared'] ?? plot.verificationLevel}</span></div>
      {mismatch && <p className="mt-1.5 text-[10px] text-[#a85143]">Mapped area differs from declared: {plot.areaCheck}</p>}
      {plot.weatherCellId && <p className="mt-1 font-data text-[8px] text-muted-foreground">Weather cell {plot.weatherCellId} (about 5 km estimate)</p>}
      {!protectedPlot && <button type="button" onClick={() => onConfirm(plot.plotId)} className="mt-2.5 flex min-h-11 w-full items-center justify-center gap-2 rounded-lg border border-[#315840] px-3 text-xs font-semibold text-[#315840] active:bg-[#dce9df]" data-testid={`button-confirm-field-${plot.plotId}`}><MapPin size={14} />{plot.locationPrecision === 'polygon' ? 'Re-check field boundary' : 'Find and confirm this field'}</button>}
    </li>;
  })}</ul>;
}

function FieldMap({ origin, current, candidates, selected, onSelect }: { origin: { lat: number; lon: number }; current?: Plot['geometry']; candidates: FieldCandidate[]; selected: string | null; onSelect: (id: string) => void }) {
  const kx = Math.cos(origin.lat * Math.PI / 180);
  const ring = (g: unknown): [number, number][] => { const c = (g as { coordinates?: number[][][] } | null)?.coordinates?.[0] ?? []; return c.map(([lon, lat]) => [lon * kx, -lat] as [number, number]); };
  const rings = candidates.map(c => ({ c, pts: ring(c.geometry) }));
  const cur = current ? ring(current) : [];
  const all = [...rings.flatMap(r => r.pts), ...cur, [origin.lon * kx, -origin.lat] as [number, number]];
  const xs = all.map(p => p[0]), ys = all.map(p => p[1]);
  const pad = Math.max(Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys)) * 0.12 || 0.0005;
  const x0 = Math.min(...xs) - pad, y0 = Math.min(...ys) - pad, w = Math.max(...xs) - Math.min(...xs) + 2 * pad, h = Math.max(...ys) - Math.min(...ys) + 2 * pad;
  const pts = (p: [number, number][]) => p.map(([x, y]) => `${x},${y}`).join(' ');
  return <svg viewBox={`${x0} ${y0} ${w} ${h}`} className="h-56 w-full rounded-lg border border-border bg-[#eef1e6]" role="img" aria-label="Candidate fields around the plot. Tap a field to select it." preserveAspectRatio="xMidYMid meet">
    {cur.length > 0 && <polygon points={pts(cur)} fill="none" stroke="#765a22" strokeWidth={w / 160} strokeDasharray={`${w / 60} ${w / 80}`} />}
    {rings.map(({ c, pts: p }, i) => <g key={c.candidateId} onClick={() => onSelect(c.candidateId)} className="cursor-pointer"><polygon points={pts(p)} fill={selected === c.candidateId ? '#315840' : '#d9b36a'} fillOpacity={selected === c.candidateId ? 0.75 : 0.5} stroke={selected === c.candidateId ? '#1d3a28' : '#765a22'} strokeWidth={w / 200} /><text x={p.reduce((a, q) => a + q[0], 0) / p.length} y={p.reduce((a, q) => a + q[1], 0) / p.length} fontSize={w / 22} textAnchor="middle" dominantBaseline="middle" fill="#1d1d1d" style={{ pointerEvents: 'none' }}>{i + 1}</text></g>)}
    <circle cx={origin.lon * kx} cy={-origin.lat} r={w / 70} fill="#a85143" stroke="#fff" strokeWidth={w / 400} />
  </svg>;
}

function FieldMatchSheet({ plotId, current, onClose, onDone }: { plotId: string; current?: Plot['geometry']; onClose: () => void; onDone: () => void }) {
  const q = useGetPlotFieldCandidates(plotId, { query: { queryKey: getGetPlotFieldCandidatesQueryKey(plotId) } });
  const [sel, setSel] = useState<string | null>(null);
  const [officer, setOfficer] = useState('');
  const [msg, setMsg] = useState('');
  const match = useMatchPlotField();
  const data = q.data;
  return <div className="fixed inset-0 z-50 flex items-end bg-black/40" role="dialog" aria-modal="true" aria-label="Confirm field" onClick={onClose}>
    <div className="max-h-[88dvh] w-full overflow-y-auto rounded-t-2xl bg-background p-4 pb-[max(1rem,env(safe-area-inset-bottom))]" onClick={e => e.stopPropagation()}>
      <div className="mx-auto mb-3 h-1 w-10 rounded-full bg-border" />
      <div className="flex items-start justify-between gap-3"><div><p className="font-data text-[9px] uppercase tracking-[.15em] text-muted-foreground">Confirm field</p><h3 className="font-display text-lg">{plotId}</h3></div><button type="button" onClick={onClose} className="min-h-11 min-w-11 rounded-lg text-lg" aria-label="Close">×</button></div>
      {q.isLoading && <Skeleton rows={3} />}
      {q.isError && <QueryError retry={() => void q.refetch()} />}
      {data && <>
        <p className="mt-2 text-[11px] leading-relaxed text-muted-foreground">{data.note} Red dot: {data.origin.hasPolygon ? 'plot centre' : 'village centre (exact plot unknown)'}. Tap a numbered field or a row.</p>
        {data.candidates.length === 0 ? <p className="mt-4 rounded-lg bg-muted p-3 text-xs">No detected fields within {data.radiusKm} km. Import field data for this area, or capture the boundary in the field.</p> : <>
          <div className="mt-3"><FieldMap origin={data.origin} current={current} candidates={data.candidates} selected={sel} onSelect={setSel} /></div>
          <ul className="mt-3 space-y-2">{data.candidates.map((c, i) => <li key={c.candidateId}><button type="button" disabled={c.alreadyMatched} onClick={() => setSel(c.candidateId)} className={`flex min-h-12 w-full items-center gap-3 rounded-lg border px-3 py-2 text-left ${sel === c.candidateId ? 'border-[#315840] bg-[#dce9df]' : 'border-border'} disabled:opacity-50`} data-testid={`button-candidate-${c.candidateId}`}>
            <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[#d9b36a] text-xs font-semibold">{i + 1}</span>
            <span className="min-w-0 flex-1"><span className="block text-xs font-semibold">{c.areaHa} ha · {c.distanceM} m away</span><span className="block text-[10px] text-muted-foreground">{c.alreadyMatched ? 'Already matched to another plot' : c.reasons.join(' · ')}</span></span>
            <span className="font-data text-[9px] text-muted-foreground">{Math.round(c.score * 100)}%</span></button></li>)}</ul>
          <input value={officer} onChange={e => setOfficer(e.target.value)} placeholder="Your full name (confirming officer)" className="mt-3 h-11 w-full rounded-lg border border-input bg-background px-3 text-sm outline-none focus:border-primary" data-testid="input-matching-officer" />
          <button type="button" disabled={!sel || officer.trim().length < 2 || match.isPending} onClick={() => { setMsg(''); match.mutate({ plotId, data: { candidateId: sel!, officerName: officer.trim() } }, { onSuccess: () => { onDone(); onClose(); }, onError: err => setMsg((err as { data?: { error?: string } })?.data?.error ?? 'Could not save the match.') }); }} className="mt-3 flex min-h-12 w-full items-center justify-center gap-2 rounded-lg bg-[#315840] px-4 text-sm font-semibold text-white disabled:opacity-50" data-testid="button-confirm-match">{match.isPending ? 'Saving' : 'Confirm: this is the farmer\u2019s field'}</button>
          {msg && <p className="mt-2 text-[11px] text-[#a85143]" role="alert">{msg}</p>}
          <p className="mt-2 text-[10px] text-muted-foreground">Confirm only after checking with the farmer or on site. Your name is recorded in the audit trail.</p></>}
      </>}
    </div></div>;
}

function Capability({ label, value, active }: { label: string; value: string; active: boolean }) {
  return <div><p className="uppercase tracking-[.12em] text-[#8d8065]">{label}</p><p className={`mt-1 font-semibold ${active ? 'text-[#315840]' : 'text-[#765a35]'}`}>{value}</p></div>;
}

function Metric({ label, value, icon, note, accent = false }: { label: string; value: number | string; icon: ReactNode; note: string; accent?: boolean }) {
  return <div className={`relative overflow-hidden rounded-xl border p-5 ${accent ? 'border-[#294d3d] bg-[#284b3b] text-[#f4f0e5]' : 'border-card-border bg-card'}`}>
    <div className={`absolute right-4 top-4 ${accent ? 'text-[#d9c17f]/80' : 'text-primary/65'}`}>{icon}</div>
    <p className={`font-data text-[10px] uppercase tracking-[.14em] ${accent ? 'text-[#e8dfca]/65' : 'text-muted-foreground'}`}>{label}</p>
    <p className="mt-3 font-display text-[39px] leading-none">{value}</p>
    <p className={`mt-3 text-[11px] ${accent ? 'text-[#e8dfca]/65' : 'text-muted-foreground'}`}>{note}</p>
  </div>;
}

function Workbench() {
  const [path, setLocation] = useLocation();
  const queryClient = useQueryClient();
  const overview = useGetOverview({ query: { queryKey: getGetOverviewQueryKey() } });
  const clustersQuery = useGetClusters({ query: { queryKey: getGetClustersQueryKey() } });
  const statusQuery = useGetAgentStatus({ query: { queryKey: getGetAgentStatusQueryKey() } });
  const health = useHealthCheck({ query: { queryKey: getHealthCheckQueryKey() } });
  const advisoriesQuery = useGetAdvisories({ query: { queryKey: getGetAdvisoriesQueryKey() } });
  const auditQuery = useGetAuditEvents({ query: { queryKey: getGetAuditEventsQueryKey() } });
  const clusters = clustersQuery.data ?? [];
  const advisories = advisoriesQuery.data ?? [];
  const [clusterId, setClusterId] = useState('');
  const activeClusterId = clusterId || clusters[0]?.clusterId || '';
  const plotsQuery = useGetClusterPlots(activeClusterId, { query: { enabled: !!activeClusterId, queryKey: getGetClusterPlotsQueryKey(activeClusterId) } });
  const evidenceQuery = useGetClusterEvidence(activeClusterId, { query: { enabled: !!activeClusterId, queryKey: getGetClusterEvidenceQueryKey(activeClusterId) } });
  const [runQuestion, setRunQuestion] = useState('');
  const [lastRun, setLastRun] = useState<EvidenceRun | null>(null);
  const [runSelection, setRunSelection] = useState<string[]>([]);
  const [submitter, setSubmitter] = useState('');
  const submitDrafts = useSubmitAgentDrafts();
  const [search, setSearch] = useState('');
  const [selectedAdvisory, setSelectedAdvisory] = useState<Advisory | null>(null);
  const [author, setAuthor] = useState('');
  const [approvalName, setApprovalName] = useState('');
  const [approvalNote, setApprovalNote] = useState('');
  const [title, setTitle] = useState('');
  const [recommendation, setRecommendation] = useState('');
  const [rationale, setRationale] = useState('');
  const [selectedEvidence, setSelectedEvidence] = useState<string[]>([]);
  const [formMessage, setFormMessage] = useState('');
  const [matchPlotId, setMatchPlotId] = useState<string | null>(null);
  const createRun = useCreateEvidenceRun();
  const createAdvisory = useCreateManualAdvisory();
  const approve = useApproveAdvisory();
  const evidence = evidenceQuery.data?.evidence ?? [];
  const currentCluster = clusters.find(c => c.clusterId === activeClusterId);
  const drafts = advisories.filter(a => a.status === 'draft');
  const filteredClusters = useMemo(() => clusters.filter(c => `${c.name} ${c.commune} ${c.department}`.toLowerCase().includes(search.toLowerCase())), [clusters, search]);

  const refreshLists = () => {
    void queryClient.invalidateQueries({ queryKey: getGetOverviewQueryKey() });
    void queryClient.invalidateQueries({ queryKey: getGetAdvisoriesQueryKey() });
    void queryClient.invalidateQueries({ queryKey: getGetAuditEventsQueryKey() });
  };
  const submitRun = async (event: FormEvent) => {
    event.preventDefault();
    if (!activeClusterId || runQuestion.trim().length < 3) return;
    try {
      const result = await createRun.mutateAsync({ data: { clusterId: activeClusterId, question: runQuestion.trim() } });
      setLastRun(result); setRunSelection([]); setFormMessage('');
      void queryClient.invalidateQueries({ queryKey: getGetClusterEvidenceQueryKey(activeClusterId) });
    } catch (err) { setFormMessage((err as { data?: { error?: string } })?.data?.error ?? 'The agent run did not complete. Please retry.'); }
  };
  const submitAdvisory = (event: FormEvent) => {
    event.preventDefault();
    setFormMessage('');
    if (selectedEvidence.length < 1) { setFormMessage('Attach at least one source record before saving this draft.'); return; }
    createAdvisory.mutate({ data: { clusterId: activeClusterId, title: title.trim(), recommendation: recommendation.trim(), rationale: rationale.trim(), authoredBy: author.trim(), evidenceIds: selectedEvidence } }, {
      onSuccess: () => {
        setTitle(''); setRecommendation(''); setRationale(''); setSelectedEvidence([]);
        setFormMessage('Officer-authored draft saved. It has not been delivered.');
        refreshLists();
      },
      onError: () => setFormMessage('The draft was not saved. Check the fields and try again.'),
    });
  };
  const submitApproval = (event: FormEvent) => {
    event.preventDefault();
    if (!selectedAdvisory) return;
    setFormMessage('');
    if (approvalName.trim().toLocaleLowerCase() === selectedAdvisory.authoredBy.trim().toLocaleLowerCase() || approvalName.trim().toLocaleLowerCase() === (selectedAdvisory.submittedBy ?? '').trim().toLocaleLowerCase()) {
      setFormMessage('A different officer must approve this draft than its author or the officer who submitted it.'); return;
    }
    approve.mutate({ advisoryId: selectedAdvisory.advisoryId, data: { officerName: approvalName.trim(), approvalNote: approvalNote.trim() } }, {
      onSuccess: updated => { setSelectedAdvisory(updated); setApprovalNote(''); setFormMessage('Approval recorded. This changes the record state only; no delivery occurred.'); refreshLists(); },
      onError: () => setFormMessage('Approval could not be recorded. Please retry.'),
    });
  };
  const page = path === '/investigate' ? 'investigate' : path === '/advisories' ? 'advisories' : path === '/audit' ? 'audit' : 'overview';

  return <Shell active={path}>
    {matchPlotId && <FieldMatchSheet plotId={matchPlotId} current={plotsQuery.data?.find(p => p.plotId === matchPlotId)?.geometry} onClose={() => setMatchPlotId(null)} onDone={() => { void plotsQuery.refetch(); refreshLists(); }} />}
      <AgentNotice status={statusQuery.data} />
    {page === 'overview' && <section className="rise">
      <SectionHeading eyebrow="Field operations · 01" title="Good morning, officer." description="A clear view of field clusters, source records, and the advice awaiting a second set of eyes." action={<div className="flex items-center gap-2 rounded-lg border border-border bg-card px-3 py-2 text-[11px] text-muted-foreground"><span className={`h-2 w-2 rounded-full ${health.data?.status === 'ok' ? 'bg-[#668a5d]' : 'bg-[#c99a50]'}`} />{health.isLoading ? 'Checking service' : health.data?.status === 'ok' ? 'Workbench connected' : 'Service status unknown'}</div>} />
      {overview.isLoading ? <Skeleton rows={2} /> : overview.isError ? <QueryError retry={() => void overview.refetch()} /> : <>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <Metric label="Active clusters" value={overview.data?.clusters ?? 0} icon={<MapPin size={19} />} note="Extension areas on record" />
          <Metric label="Plots in register" value={overview.data?.plots ?? 0} icon={<Sprout size={19} />} note="Local test records" />
          <Metric label="Awaiting review" value={overview.data?.pendingAdvisories ?? 0} icon={<FileText size={19} />} note="Drafts awaiting approval" accent />
          <Metric label="Approved records" value={overview.data?.approvedAdvisories ?? 0} icon={<CheckCircle2 size={19} />} note="Approved by named officers" />
        </div>
        <div className="mt-7 grid gap-6 xl:grid-cols-[minmax(0,1.55fr)_minmax(320px,.85fr)]">
          <section className="rounded-xl border border-card-border bg-card">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-5 py-4"><div><p className="font-data text-[9px] uppercase tracking-[.16em] text-muted-foreground">Coverage register</p><h2 className="mt-1 font-display text-[22px]">Field clusters</h2></div><label className="flex h-9 items-center gap-2 rounded-lg border border-input bg-background px-3"><Search size={14} className="text-muted-foreground" /><input value={search} onChange={e => setSearch(e.target.value)} placeholder="Find a cluster" className="w-32 bg-transparent text-xs outline-none placeholder:text-muted-foreground/70 sm:w-44" data-testid="input-cluster-search" /></label></div>
            <div className="divide-y divide-border">{clustersQuery.isLoading ? <div className="p-5"><Skeleton /></div> : clustersQuery.isError ? <div className="p-5"><QueryError retry={() => void clustersQuery.refetch()} /></div> : filteredClusters.length === 0 ? <div className="px-5 py-12 text-center"><MapPin className="mx-auto text-muted-foreground/40" size={24} /><p className="mt-3 text-sm font-semibold">{clusters.length ? 'No clusters match this search' : 'No clusters on record'}</p><p className="mt-1 text-xs text-muted-foreground">Cluster records will appear when available from the service.</p></div> : filteredClusters.map((cluster, i) => <div key={cluster.clusterId} className="grid gap-3 px-5 py-4 transition-colors hover:bg-muted/30 sm:grid-cols-[1fr_auto] sm:items-center" data-testid={`row-cluster-${cluster.clusterId}`}>
              <div className="flex items-start gap-3"><div className={`mt-0.5 grid h-9 w-9 shrink-0 place-items-center rounded-lg ${i % 2 ? 'bg-[#e8dfc9] text-[#7b6739]' : 'bg-[#dce7dc] text-[#3d664c]'}`}><Sprout size={17} /></div><div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><h3 className="text-sm font-semibold">{cluster.name}</h3><DataTag /></div><p className="mt-1 text-xs text-muted-foreground">{cluster.commune}, {cluster.department}</p><p className="mt-2 font-data text-[10px] text-muted-foreground">{cluster.householdCount} households <span className="mx-1 text-border">/</span> {cluster.plotCount} plots</p></div></div>
              <div className="flex items-center justify-between gap-4 sm:justify-end"><div className="text-right"><p className="font-data text-lg">{cluster.openPestReports}</p><p className="text-[10px] text-muted-foreground">open pest reports</p></div><Link href="/investigate" onClick={() => setClusterId(cluster.clusterId)} className="inline-flex items-center gap-1.5 rounded-lg border border-border px-3 py-2 text-[11px] font-semibold hover:border-primary/40 hover:bg-muted" data-testid={`link-investigate-${cluster.clusterId}`}>Inspect <ArrowRight size={13} /></Link></div>
            </div>)}</div>
          </section>
          <section className="overflow-hidden rounded-xl border border-card-border bg-card">
            <div className="flex items-center justify-between border-b border-border px-5 py-4"><div><p className="font-data text-[9px] uppercase tracking-[.16em] text-muted-foreground">Named human review</p><h2 className="mt-1 font-display text-[22px]">Review queue</h2></div><Link href="/advisories" className="text-[11px] font-semibold text-primary hover:underline" data-testid="link-all-advisories">All drafts <ArrowRight size={13} className="ml-1 inline" /></Link></div>
            <div className="divide-y divide-border">{advisoriesQuery.isLoading ? <div className="p-5"><Skeleton rows={2} /></div> : advisoriesQuery.isError ? <div className="p-5"><QueryError retry={() => void advisoriesQuery.refetch()} /></div> : drafts.length ? drafts.slice(0, 4).map(draft => <button key={draft.advisoryId} onClick={() => { setSelectedAdvisory(draft); setLocation('/advisories'); }} className="block w-full px-5 py-4 text-left transition-colors hover:bg-muted/30" data-testid={`button-review-${draft.advisoryId}`}><div className="flex items-start justify-between gap-3"><div className="min-w-0"><p className="truncate text-sm font-semibold">{draft.title}</p><p className="mt-1 text-xs text-muted-foreground">By {draft.authoredBy} · {formatDate(draft.createdAt)}</p></div><StatusPill tone="warning">Draft</StatusPill></div><p className="mt-2 line-clamp-2 text-xs leading-relaxed text-muted-foreground">{draft.recommendation}</p></button>) : <div className="px-5 py-10 text-center"><FileCheck2 size={23} className="mx-auto text-muted-foreground/40" /><p className="mt-3 text-sm font-semibold">Review queue is clear</p><p className="mt-1 text-xs text-muted-foreground">Agent and officer drafts appear here once submitted.</p><Link href="/advisories" className="mt-4 inline-flex items-center gap-1.5 text-xs font-semibold text-primary" data-testid="link-create-first-draft">Write an advisory <ArrowRight size={13} /></Link></div>}</div>
            <div className="border-t border-border bg-muted/30 px-5 py-3 font-data text-[9px] uppercase tracking-[.1em] text-muted-foreground">Approval requires a different named officer</div>
          </section>
        </div>
        <div className="mt-6 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border bg-[#ede7d8]/60 px-4 py-3 text-[11px] text-muted-foreground"><span>Data tier <strong className="ml-1 font-data font-medium text-foreground">{overview.data?.dataTier ?? 'local_test_data'}</strong> <span className="mx-2">·</span> Last updated {formatTime(overview.data?.lastUpdated)}</span><span>Sample records only — do not treat as field observations.</span></div>
      </>}
    </section>}

    {page === 'investigate' && <section className="rise">
      <SectionHeading eyebrow="Source inspection · 02" title="Investigate a cluster" description="Review recorded plot, rainfall, crop calendar, pest and weather evidence. Every item stays attached to its source record." action={<label className="flex min-w-[220px] items-center gap-2 rounded-lg border border-input bg-card px-3 py-2.5"><MapPin size={15} className="text-muted-foreground" /><select value={activeClusterId} onChange={e => { setClusterId(e.target.value); setLastRun(null); }} className="w-full bg-transparent text-xs outline-none" data-testid="select-investigation-cluster">{clusters.length ? clusters.map(c => <option key={c.clusterId} value={c.clusterId}>{c.name} · {c.commune}</option>) : <option value="">No clusters available</option>}</select><ChevronDown size={14} /></label>} />
      {clustersQuery.isLoading ? <Skeleton /> : clustersQuery.isError ? <QueryError retry={() => void clustersQuery.refetch()} /> : !clusters.length ? <EmptyState icon={<MapPin size={22} />} title="No cluster records yet" detail="When cluster records are available, their evidence register will appear here." /> : <>
        <div className="mb-5 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-card-border bg-card px-5 py-4"><div><p className="font-data text-[9px] uppercase tracking-[.15em] text-muted-foreground">Selected cluster</p><h2 className="mt-1 font-display text-[24px]">{currentCluster?.name}</h2><p className="mt-1 text-xs text-muted-foreground">{currentCluster?.commune}, {currentCluster?.department} <span className="mx-1">·</span> {currentCluster?.householdCount} households</p></div><div className="flex gap-2"><StatusPill>{currentCluster?.plotCount ?? 0} plots</StatusPill><StatusPill tone={(currentCluster?.openPestReports ?? 0) > 0 ? 'warning' : 'good'}>{currentCluster?.openPestReports ?? 0} pest reports</StatusPill></div></div>
        <div className="grid gap-5 xl:grid-cols-[minmax(0,1.5fr)_minmax(320px,.8fr)]">
          <div className="space-y-5">
            <section className="rounded-xl border border-card-border bg-card">
              <div className="flex items-center justify-between border-b border-border px-5 py-4"><div><p className="font-data text-[9px] uppercase tracking-[.15em] text-muted-foreground">Recorded source material</p><h3 className="mt-1 font-display text-[21px]">Evidence register</h3></div><DataTag /></div>
              {evidenceQuery.isLoading ? <div className="p-5"><Skeleton rows={4} /></div> : evidenceQuery.isError ? <div className="p-5"><QueryError retry={() => void evidenceQuery.refetch()} /></div> : evidence.length ? <div className="divide-y divide-border">{evidence.map(item => <EvidenceRow key={item.evidenceId} item={item} selectable onToggle={() => setSelectedEvidence(prev => prev.includes(item.evidenceId) ? prev.filter(id => id !== item.evidenceId) : [...prev, item.evidenceId])} selected={selectedEvidence.includes(item.evidenceId)} />)}</div> : <EmptyState icon={<Search size={22} />} title="No evidence records" detail="The service returned no evidence for this cluster. Nothing has been inferred or filled in." />}
              {!!evidenceQuery.data?.sourceSummary?.length && <div className="border-t border-border px-5 py-3"><p className="font-data text-[9px] uppercase tracking-[.12em] text-muted-foreground">Source summary</p><div className="mt-2 flex flex-wrap gap-2">{evidenceQuery.data.sourceSummary.map(source => <span key={source} className="rounded-md bg-muted px-2 py-1 text-[10px] text-muted-foreground">{source}</span>)}</div></div>}
            </section>
            <section className="rounded-xl border border-card-border bg-card">
              <div className="flex items-center justify-between border-b border-border px-5 py-4"><div><p className="font-data text-[9px] uppercase tracking-[.15em] text-muted-foreground">Household records</p><h3 className="mt-1 font-display text-[21px]">Plots in this cluster</h3></div><span className="font-data text-[10px] text-muted-foreground">{plotsQuery.data?.length ?? 0} records</span></div>
              {plotsQuery.isLoading ? <div className="p-5"><Skeleton rows={3} /></div> : plotsQuery.isError ? <div className="p-5"><QueryError retry={() => void plotsQuery.refetch()} /></div> : plotsQuery.data?.length ? <PlotCards plots={plotsQuery.data} onConfirm={setMatchPlotId} /> : <EmptyState icon={<Sprout size={22} />} title="No plot records" detail="There are no household plot records for this cluster yet." />}
            </section>
          </div>
          <div className="space-y-5">
            <section className="rounded-xl border border-[#bdb28f] bg-[#efe8d8]/75 p-5">
              <div className="flex items-start gap-3"><div className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-[#dfd1ae] text-[#705a31]"><Microscope size={17} /></div><div><p className="font-data text-[9px] uppercase tracking-[.14em] text-[#806c42]">Agent-assisted analysis</p><h3 className="mt-1 font-display text-[21px]">Ask the agent</h3></div></div>
              <p className="mt-3 text-xs leading-relaxed text-[#6d6553]">The agent decides which evidence tools to call, reads each result, and drafts cited household recommendations. If evidence is missing it says so. Nothing is sent to farmers.</p>
              <form onSubmit={submitRun} className="mt-4">
                <label className="mb-1.5 block text-[11px] font-semibold">Question for the agent</label><textarea value={runQuestion} onChange={e => setRunQuestion(e.target.value)} minLength={3} maxLength={500} required rows={3} placeholder="For example: Which maize households in this cluster should consider delaying planting?" className="w-full resize-y rounded-lg border border-[#cfc3a5] bg-[#faf7ee] px-3 py-2.5 text-xs leading-relaxed outline-none placeholder:text-[#9c927a] focus:border-primary" data-testid="input-evidence-question" />
                <button type="submit" disabled={createRun.isPending || runQuestion.trim().length < 3} className="mt-3 flex w-full items-center justify-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-xs font-semibold text-primary-foreground transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50" data-testid="button-run-evidence">{createRun.isPending ? <><RefreshCw className="animate-spin" size={14} />Agent is working</> : <>Ask the agent <ArrowRight size={14} /></>}</button>
              </form>
              {formMessage && <p className="mt-3 text-xs text-[#a85143]" role="status">{formMessage}</p>}
              {lastRun && <AgentRunPanel run={lastRun} selection={runSelection} onToggle={id => setRunSelection(prev => prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id])} submitter={submitter} setSubmitter={setSubmitter} pending={submitDrafts.isPending} message={formMessage} onSubmit={() => { setFormMessage(''); submitDrafts.mutate({ runId: lastRun.runId, data: { officerName: submitter.trim(), householdIds: runSelection } }, { onSuccess: created => { setRunSelection([]); setFormMessage(`${created.length} draft(s) submitted. Each needs approval by a different named officer.`); refreshLists(); }, onError: err => setFormMessage((err as { data?: { error?: string } })?.data?.error ?? 'Drafts could not be submitted.') }); }} />}
            </section>
            <div className="rounded-xl border border-border bg-card p-5"><div className="flex items-center gap-2"><CloudRain size={16} className="text-[#6b8790]" /><h3 className="text-sm font-semibold">Weather source status</h3></div><p className="mt-2 text-xs leading-relaxed text-muted-foreground">Live AccuWeather is unavailable. Any weather or rainfall records shown above are labeled local test data and are not a live forecast.</p><div className="mt-3 flex items-center justify-between border-t border-border pt-3"><span className="font-data text-[9px] uppercase tracking-wider text-muted-foreground">Provider: AccuWeather</span><StatusPill tone="warning">Not live</StatusPill></div></div>
          </div>
        </div>
      </>}
    </section>}

    {page === 'advisories' && <section className="rise">
      <SectionHeading eyebrow="Officer-authored guidance · 03" title="Advisories" description="Write a manual draft grounded in attached source records. Approval is a separate, named officer action." action={<StatusPill tone="warning">No AI draft generation</StatusPill>} />
      <div className="mb-5 rounded-xl border border-[#cbbd9c] bg-[#f0e8d3]/75 px-5 py-3.5 text-xs leading-relaxed text-[#655d4b]"><strong>Human approval is mandatory.</strong> Drafts come from an officer or from the agent (submitted by a named officer), are tied to evidence records, and must be approved by a different named officer. Approval updates the record; it does not deliver advice to farmers.</div>
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.05fr)_minmax(360px,.95fr)]">
        <section className="rounded-xl border border-card-border bg-card">
          <div className="border-b border-border px-5 py-4"><p className="font-data text-[9px] uppercase tracking-[.15em] text-muted-foreground">Create a record</p><h2 className="mt-1 font-display text-[22px]">Write manual draft</h2></div>
          <form onSubmit={submitAdvisory} className="space-y-4 p-5">
            <label className="block"><span className="mb-1.5 block text-[11px] font-semibold">Cluster</span><select value={activeClusterId} onChange={e => { setClusterId(e.target.value); setSelectedEvidence([]); }} required className="h-10 w-full rounded-lg border border-input bg-background px-3 text-xs outline-none focus:border-primary" data-testid="select-advisory-cluster">{clusters.length ? clusters.map(c => <option key={c.clusterId} value={c.clusterId}>{c.name} · {c.commune}</option>) : <option value="">No clusters available</option>}</select></label>
            <label className="block"><span className="mb-1.5 block text-[11px] font-semibold">Draft title</span><input value={title} onChange={e => setTitle(e.target.value)} required minLength={3} maxLength={160} placeholder="A concise, specific subject" className="h-10 w-full rounded-lg border border-input bg-background px-3 text-xs outline-none focus:border-primary" data-testid="input-advisory-title" /></label>
            <label className="block"><span className="mb-1.5 block text-[11px] font-semibold">Recommendation</span><textarea value={recommendation} onChange={e => setRecommendation(e.target.value)} required minLength={3} maxLength={2000} rows={4} placeholder="Write the proposed action in your own words." className="w-full resize-y rounded-lg border border-input bg-background px-3 py-2.5 text-xs leading-relaxed outline-none focus:border-primary" data-testid="input-advisory-recommendation" /></label>
            <label className="block"><span className="mb-1.5 block text-[11px] font-semibold">Rationale</span><textarea value={rationale} onChange={e => setRationale(e.target.value)} required minLength={3} maxLength={3000} rows={3} placeholder="Explain how the attached source evidence supports this draft." className="w-full resize-y rounded-lg border border-input bg-background px-3 py-2.5 text-xs leading-relaxed outline-none focus:border-primary" data-testid="input-advisory-rationale" /></label>
            <label className="block"><span className="mb-1.5 block text-[11px] font-semibold">Authoring officer name</span><input value={author} onChange={e => setAuthor(e.target.value)} required minLength={2} maxLength={120} placeholder="Enter the officer's name" className="h-10 w-full rounded-lg border border-input bg-background px-3 text-xs outline-none focus:border-primary" data-testid="input-advisory-author" /><span className="mt-1 block text-[10px] text-muted-foreground">Prototype identity is self-attested, not authenticated.</span></label>
            <div><div className="mb-2 flex items-center justify-between"><span className="text-[11px] font-semibold">Attach evidence sources <span className="text-[#a85143]">*</span></span><Link href="/investigate" className="text-[10px] font-semibold text-primary hover:underline" data-testid="link-inspect-evidence">Inspect records <ArrowRight size={12} className="inline" /></Link></div>
              {evidenceQuery.isLoading ? <Skeleton rows={2} /> : evidenceQuery.isError ? <QueryError retry={() => void evidenceQuery.refetch()} /> : evidence.length ? <div className="max-h-[200px] space-y-1 overflow-y-auto rounded-lg border border-border p-2">{evidence.map(item => <label key={item.evidenceId} className="flex cursor-pointer items-start gap-2.5 rounded-md px-2 py-2 hover:bg-muted/50"><input type="checkbox" checked={selectedEvidence.includes(item.evidenceId)} onChange={() => setSelectedEvidence(prev => prev.includes(item.evidenceId) ? prev.filter(id => id !== item.evidenceId) : [...prev, item.evidenceId])} className="mt-0.5 accent-[#315840]" data-testid={`checkbox-evidence-${item.evidenceId}`} /><span className="min-w-0 flex-1"><span className="block text-[11px] font-semibold">{item.label}</span><span className="mt-0.5 block truncate text-[9px] text-muted-foreground">{item.sourceName} · {item.sourceRecordId}</span></span><span className="font-data text-[8px] uppercase text-muted-foreground">{item.kind.replace('_', ' ')}</span></label>)}</div> : <div className="rounded-lg border border-dashed border-border px-3 py-4 text-center text-[10px] text-muted-foreground">No source records to attach for this cluster. A draft cannot be saved without evidence.</div>}</div>
            {formMessage && <p role="status" className="rounded-lg bg-[#e7eee5] px-3 py-2.5 text-xs text-[#315840]">{formMessage}</p>}
            <button type="submit" disabled={createAdvisory.isPending || !clusters.length || evidence.length === 0} className="flex w-full items-center justify-center gap-2 rounded-lg bg-primary px-4 py-3 text-xs font-semibold text-primary-foreground hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50" data-testid="button-save-advisory">{createAdvisory.isPending ? <><RefreshCw size={14} className="animate-spin" />Saving draft</> : <><Plus size={14} />Save officer-authored draft</>}</button>
          </form>
        </section>
        <div className="space-y-5">
          <section className="rounded-xl border border-card-border bg-card">
            <div className="flex items-center justify-between border-b border-border px-5 py-4"><div><p className="font-data text-[9px] uppercase tracking-[.15em] text-muted-foreground">Review queue</p><h2 className="mt-1 font-display text-[22px]">Drafts to review <span className="font-sans text-sm text-muted-foreground">({drafts.length})</span></h2></div><Filter size={15} className="text-muted-foreground" /></div>
            {advisoriesQuery.isLoading ? <div className="p-5"><Skeleton rows={2} /></div> : advisoriesQuery.isError ? <div className="p-5"><QueryError retry={() => void advisoriesQuery.refetch()} /></div> : drafts.length ? <div className="max-h-[300px] divide-y divide-border overflow-y-auto">{drafts.map(draft => <button key={draft.advisoryId} onClick={() => { setSelectedAdvisory(draft); setFormMessage(''); }} className={`w-full px-5 py-3.5 text-left hover:bg-muted/30 ${selectedAdvisory?.advisoryId === draft.advisoryId ? 'bg-[#e9e4d5]/70' : ''}`} data-testid={`button-select-draft-${draft.advisoryId}`}><div className="flex items-start justify-between gap-2"><div><p className="text-xs font-semibold">{draft.title}</p><p className="mt-1 text-[10px] text-muted-foreground">{draft.authoredBy} · {formatDate(draft.createdAt)}</p></div><StatusPill tone="warning">Draft</StatusPill></div></button>)}</div> : <EmptyState icon={<FileText size={22} />} title="No drafts awaiting review" detail="New officer-authored drafts will be listed here." />}
          </section>
          {selectedAdvisory ? <section className="rounded-xl border border-card-border bg-card">
            <div className="flex items-center justify-between border-b border-border px-5 py-4"><div><p className="font-data text-[9px] uppercase tracking-[.15em] text-muted-foreground">Record detail</p><h2 className="mt-1 font-display text-[21px]">{selectedAdvisory.title}</h2></div><StatusPill tone={selectedAdvisory.status === 'approved' ? 'good' : 'warning'}>{selectedAdvisory.status}</StatusPill></div>
            <div className="space-y-4 p-5"><div><p className="font-data text-[9px] uppercase tracking-[.12em] text-muted-foreground">Recommendation</p><p className="mt-1.5 text-xs leading-relaxed">{selectedAdvisory.recommendation}</p></div><div><p className="font-data text-[9px] uppercase tracking-[.12em] text-muted-foreground">Rationale</p><p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">{selectedAdvisory.rationale}</p></div><div><p className="font-data text-[9px] uppercase tracking-[.12em] text-muted-foreground">Authored by</p><p className="mt-1 text-xs font-semibold">{selectedAdvisory.authoredBy}</p>{selectedAdvisory.submittedBy && <p className="mt-1 text-[10px] text-muted-foreground">Submitted for review by {selectedAdvisory.submittedBy} · agent run <span className="font-data">{selectedAdvisory.agentRunId}</span></p>}</div><div><p className="font-data text-[9px] uppercase tracking-[.12em] text-muted-foreground">Cited evidence</p><div className="mt-2 space-y-2">{selectedAdvisory.evidence.map(item => <div key={item.evidenceId} className="rounded-lg bg-muted/50 px-3 py-2"><p className="text-[11px] font-semibold">{item.label}</p><p className="mt-1 text-[9px] text-muted-foreground">{item.sourceName} · {item.sourceRecordId} <span className="font-data">· {item.dataTier}</span></p></div>)}</div></div>
              {selectedAdvisory.status === 'draft' ? <form onSubmit={submitApproval} className="space-y-3 border-t border-border pt-4"><div><p className="font-data text-[9px] uppercase tracking-[.12em] text-[#806c42]">Second-officer approval</p><p className="mt-1 text-[10px] text-muted-foreground">Approver must be a different named officer from {selectedAdvisory.authoredBy}.</p></div><label className="block"><span className="mb-1.5 block text-[10px] font-semibold">Approving officer</span><input value={approvalName} onChange={e => setApprovalName(e.target.value)} required minLength={2} maxLength={120} className="h-9 w-full rounded-lg border border-input bg-background px-3 text-xs outline-none focus:border-primary" placeholder="Enter a different officer name" data-testid="input-approval-officer" /></label><label className="block"><span className="mb-1.5 block text-[10px] font-semibold">Approval note <span className="font-normal text-muted-foreground">· optional</span></span><textarea value={approvalNote} onChange={e => setApprovalNote(e.target.value)} maxLength={1000} rows={2} className="w-full rounded-lg border border-input bg-background px-3 py-2 text-xs outline-none focus:border-primary" placeholder="Record any review note" data-testid="input-approval-note" /></label><button type="submit" disabled={approve.isPending} className="flex w-full items-center justify-center gap-2 rounded-lg bg-[#315840] px-4 py-2.5 text-xs font-semibold text-white hover:opacity-90 disabled:opacity-50" data-testid="button-approve-advisory">{approve.isPending ? 'Recording approval' : <><Check size={14} />Approve as named officer</>}</button></form> : <div className="rounded-lg bg-[#e3ece2] p-3"><p className="text-xs font-semibold text-[#315840]">Approved by {selectedAdvisory.approvedBy}</p><p className="mt-1 text-[10px] text-[#52715a]">{selectedAdvisory.approvalNote || 'No approval note recorded.'} · {formatDate(selectedAdvisory.approvedAt)}</p></div>}
              {formMessage && <p role="status" className="text-xs text-[#765a35]">{formMessage}</p>}
              <p className="border-t border-border pt-3 text-[10px] leading-relaxed text-muted-foreground">Approval records officer review only. This workbench has no farmer delivery channel.</p>
            </div>
          </section> : <div className="rounded-xl border border-dashed border-border bg-card/50 px-5 py-10 text-center"><FileCheck2 className="mx-auto text-muted-foreground/45" size={22} /><p className="mt-3 text-sm font-semibold">Select a draft to inspect</p><p className="mt-1 text-xs text-muted-foreground">Review its rationale, source citations, and approval history.</p></div>}
          {advisories.filter(a => a.status === 'approved').length > 0 && <section className="rounded-xl border border-card-border bg-card"><div className="border-b border-border px-5 py-4"><p className="font-data text-[9px] uppercase tracking-[.15em] text-muted-foreground">Completed review</p><h2 className="mt-1 font-display text-[19px]">Approved records</h2></div><div className="divide-y divide-border">{advisories.filter(a => a.status === 'approved').map(item => <button key={item.advisoryId} onClick={() => { setSelectedAdvisory(item); setFormMessage(''); }} className="flex w-full items-center justify-between gap-3 px-5 py-3 text-left hover:bg-muted/30" data-testid={`button-approved-${item.advisoryId}`}><span><span className="block text-xs font-semibold">{item.title}</span><span className="mt-1 block text-[10px] text-muted-foreground">Approved by {item.approvedBy}</span></span><StatusPill tone="good">Approved</StatusPill></button>)}</div></section>}
        </div>
      </div>
    </section>}

    {page === 'audit' && <section className="rise">
      <SectionHeading eyebrow="Provenance ledger · 04" title="Audit trail" description="Recent record activity, actor attribution, and source tier. Provenance is part of the work, not a footnote." action={<button onClick={() => void auditQuery.refetch()} className="inline-flex items-center gap-2 rounded-lg border border-border bg-card px-3 py-2.5 text-xs font-semibold hover:bg-muted" data-testid="button-refresh-audit"><RefreshCw size={14} />Refresh</button>} />
      <div className="mb-5 grid gap-3 sm:grid-cols-3"><div className="rounded-xl border border-card-border bg-card p-4"><p className="font-data text-[9px] uppercase tracking-[.12em] text-muted-foreground">Recent events</p><p className="mt-2 font-display text-3xl">{auditQuery.data?.length ?? 0}</p></div><div className="rounded-xl border border-card-border bg-card p-4"><p className="font-data text-[9px] uppercase tracking-[.12em] text-muted-foreground">Identity mode</p><p className="mt-2 text-sm font-semibold">Self-attested prototype</p><p className="mt-1 text-[10px] text-muted-foreground">Not authenticated identity</p></div><div className="rounded-xl border border-card-border bg-card p-4"><p className="font-data text-[9px] uppercase tracking-[.12em] text-muted-foreground">Data provenance</p><p className="mt-2 text-sm font-semibold">Local test data</p><p className="mt-1 text-[10px] text-muted-foreground">No live external source represented</p></div></div>
      <section className="overflow-hidden rounded-xl border border-card-border bg-card">
        <div className="flex items-center justify-between border-b border-border px-5 py-4"><div><p className="font-data text-[9px] uppercase tracking-[.15em] text-muted-foreground">Chronological record</p><h2 className="mt-1 font-display text-[22px]">Recent activity</h2></div><StatusPill>{auditQuery.data?.length ?? 0} events</StatusPill></div>
        {auditQuery.isLoading ? <div className="p-5"><Skeleton rows={5} /></div> : auditQuery.isError ? <div className="p-5"><QueryError retry={() => void auditQuery.refetch()} /></div> : auditQuery.data?.length ? <div className="divide-y divide-border">{auditQuery.data.map((event, i) => <div key={event.eventId} className="grid gap-3 px-5 py-4 sm:grid-cols-[28px_1fr_auto] sm:items-start" data-testid={`row-audit-${event.eventId}`}><div className={`mt-0.5 grid h-7 w-7 place-items-center rounded-lg ${i === 0 ? 'bg-[#e7ddc1] text-[#705a31]' : 'bg-muted text-muted-foreground'}`}><Activity size={14} /></div><div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><p className="text-xs font-semibold">{event.summary}</p><StatusPill>{event.eventType.replaceAll('_', ' ')}</StatusPill></div><p className="mt-1.5 text-[11px] text-muted-foreground">Actor <span className="font-medium text-foreground">{event.actor}</span></p><p className="mt-1 font-data text-[9px] text-muted-foreground">{event.eventId}{event.advisoryId ? ` · Advisory ${event.advisoryId}` : ''}</p></div><div className="flex items-center justify-between gap-3 sm:flex-col sm:items-end"><span className="text-[10px] text-muted-foreground">{formatTime(event.occurredAt)}</span>{event.dataTier && <DataTag />}</div></div>)}</div> : <EmptyState icon={<ClipboardList size={22} />} title="No audit events recorded" detail="Activity will be listed here when the service returns audit records. No events are fabricated for display." />}
      </section>
      <div className="mt-5 rounded-xl border border-border bg-[#ede7d8]/60 p-4"><div className="flex gap-3"><Fingerprint size={17} className="mt-0.5 shrink-0 text-[#806c42]" /><div><p className="text-xs font-semibold">Identity and delivery constraints</p><p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">Names entered for draft authorship and approval are self-attested in this prototype. The system does not establish authenticated officer identity, and approved records are not sent to farmers.</p></div></div></div>
    </section>}
  </Shell>;
}

function EvidenceRow({ item, selectable, selected, onToggle }: { item: EvidenceItem; selectable?: boolean; selected?: boolean; onToggle?: () => void }) {
  const icon = item.kind === 'rainfall' || item.kind === 'forecast' ? <CloudRain size={15} /> : item.kind === 'pest_report' ? <CircleAlert size={15} /> : item.kind === 'crop_calendar' ? <ClipboardList size={15} /> : <Sprout size={15} />;
  const tone = item.kind === 'pest_report' ? 'bg-[#f0e2d5] text-[#915d3e]' : item.kind === 'rainfall' || item.kind === 'forecast' ? 'bg-[#e0e9eb] text-[#52717a]' : 'bg-[#e0e9df] text-[#45674d]';
  return <div className={`flex gap-3 px-5 py-4 ${selected ? 'bg-[#e9e4d5]/65' : ''}`} data-testid={`record-evidence-${item.evidenceId}`}>
    {selectable && <input type="checkbox" checked={!!selected} onChange={onToggle} aria-label={`Attach ${item.label}`} className="mt-2 accent-[#315840]" data-testid={`checkbox-evidence-${item.evidenceId}`} />}
    <div className={`mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-lg ${tone}`}>{icon}</div>
    <div className="min-w-0 flex-1"><div className="flex flex-wrap items-center gap-2"><h4 className="text-xs font-semibold">{item.label}</h4><span className="font-data text-[8px] uppercase tracking-[.08em] text-muted-foreground">{item.kind.replaceAll('_', ' ')}</span></div><p className="mt-1.5 text-[11px] leading-relaxed text-muted-foreground">{item.detail}</p><div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[9px] text-muted-foreground"><span>{item.sourceName}</span><span className="font-data">{item.sourceRecordId}</span><span>{formatDate(item.observedAt)}</span><span>Source status: {item.sourceStatus}</span></div><div className="mt-2"><DataTag /></div></div>
    {selectable && <span className="mt-1 hidden text-[9px] text-muted-foreground sm:block">{selected ? 'Attached' : 'Attach'}</span>}
  </div>;
}

function EmptyState({ icon, title, detail }: { icon: ReactNode; title: string; detail: string }) {
  return <div className="px-5 py-11 text-center"><div className="mx-auto grid h-10 w-10 place-items-center rounded-xl bg-muted text-muted-foreground/65">{icon}</div><h3 className="mt-3 text-sm font-semibold">{title}</h3><p className="mx-auto mt-1 max-w-sm text-xs leading-relaxed text-muted-foreground">{detail}</p></div>;
}

function App() {
  return <QueryClientProvider client={queryClient}><TooltipProvider><ErrorBoundary><Switch>
    <Route path="/" component={Workbench} />
    <Route path="/investigate" component={Workbench} />
    <Route path="/advisories" component={Workbench} />
    <Route path="/audit" component={Workbench} />
    <Route><main className="grid min-h-[100dvh] place-items-center bg-background p-5"><div className="max-w-md rounded-2xl border border-border bg-card p-8 text-center"><Sprout size={25} className="mx-auto text-primary" /><h1 className="mt-4 font-display text-3xl">This field record is not on the map.</h1><p className="mt-2 text-sm text-muted-foreground">That route is not part of the Herosion workbench.</p><Link href="/" className="mt-5 inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-xs font-semibold text-primary-foreground" data-testid="link-return-home">Return to overview <ArrowRight size={14} /></Link></div></main></Route>
  </Switch></ErrorBoundary><Toaster /></TooltipProvider></QueryClientProvider>;
}

export default App;
