import { useCallback, useEffect, useMemo, useState } from 'react'
import { Bar, Line } from 'react-chartjs-2'
import { Corridors, Planning, errorText } from '../api/client'
import { baseOptions } from '../components/charts'
import Header from '../components/Header.jsx'
import InfoTip from '../components/InfoTip.jsx'
import { useCorridorNames } from '../hooks/useCorridorNames'

// Colours validated as a pair (colour-blind safe, >=3:1 on white).
const PAX = '#2563eb'
const GOODS = '#d97706'
const BASE = '#0d9488'
const SCEN = '#7c3aed'

// Planning Lab: passenger + goods traffic forecast, and in-memory what-if runs.
export default function PlanningLabPage() {
  return (
    <>
      <Header title="Planning Lab" subtitle="Traffic forecast and what-if simulation — nothing here changes the live plan" />
      <div className="p-6 space-y-6">
        <ForecastSection />
        <WhatIfSection />
      </div>
    </>
  )
}

/* ------------------------------------------------------------------ forecast */
function ForecastSection() {
  const [corridors, setCorridors] = useState([])
  const [corridor, setCorridor] = useState('')
  const [days, setDays] = useState(7)
  const [data, setData] = useState(null)
  const [err, setErr] = useState('')
  const corridorName = useCorridorNames()

  useEffect(() => {
    Corridors.list().then((list) => {
      setCorridors(list)
      if (list.length) setCorridor((c) => c || list[0].corridor_id)
    }).catch(() => {})
  }, [])

  useEffect(() => {
    if (!corridor) return
    setErr('')
    Planning.forecast({ corridor_id: corridor, days }).then(setData).catch((e) => setErr(errorText(e)))
  }, [corridor, days])

  if (!corridors.length) {
    return <Card title="Train + goods traffic forecast"><div className="text-sm text-slate-400">Run the AI Planner first to load corridors and running data.</div></Card>
  }

  const m = data?.model || {}
  const hourly = data?.hourly_profile || []
  const stacked = {
    labels: hourly.map((h) => `${String(h.hour).padStart(2, '0')}:00`),
    datasets: [
      { label: 'Passenger', data: hourly.map((h) => h.pax), backgroundColor: PAX, borderColor: '#fff', borderWidth: 1, borderRadius: 4 },
      { label: 'Goods', data: hourly.map((h) => h.goods), backgroundColor: GOODS, borderColor: '#fff', borderWidth: 1, borderRadius: 4 },
    ],
  }
  const daily = data?.daily || []
  const line = {
    labels: daily.map((d) => new Date(d.date).toLocaleDateString('en-IN', { weekday: 'short', day: '2-digit', month: 'short' })),
    datasets: [
      { label: 'Passenger', data: daily.map((d) => d.pax), borderColor: PAX, backgroundColor: PAX, borderWidth: 2, pointRadius: 4 },
      { label: 'Goods', data: daily.map((d) => d.goods), borderColor: GOODS, backgroundColor: GOODS, borderWidth: 2, pointRadius: 4 },
    ],
  }
  const trainsAxis = { beginAtZero: true, title: { display: true, text: 'trains', font: { size: 10 } }, grid: { color: '#f1f5f9' } }

  return (
    <Card
      title="Train + goods traffic forecast"
      info="Passenger trains come from the timetable; goods trains are not timetabled, so they are forecast from recent running history. Each maintenance window is priced by the trains it would hold."
      right={
        <div className="flex gap-2">
          <select value={corridor} onChange={(e) => setCorridor(e.target.value)} className={SELECT}>
            {corridors.map((c) => <option key={c.corridor_id} value={c.corridor_id}>{c.name}</option>)}
          </select>
          <select value={days} onChange={(e) => setDays(Number(e.target.value))} className={SELECT}>
            {[7, 14].map((d) => <option key={d} value={d}>{d} days</option>)}
          </select>
        </div>
      }
    >
      {err && <div className="text-sm text-red-600 mb-2">{err}</div>}
      {data && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
            <Tile label="Quietest 3-hour band" value={`${data.quietest_band?.start}–${data.quietest_band?.end}`} sub={`≈${data.quietest_band?.weighted_trains} weighted trains`} />
            <Tile label="Trains / day (avg)" value={Math.round(daily.reduce((a, d) => a + d.pax + d.goods, 0) / (daily.length || 1))}
              sub={`${Math.round(daily.reduce((a, d) => a + d.goods, 0) / (daily.length || 1))} goods`} />
            <Tile label="Forecast error" value={m.mae_trains_per_hour != null ? `${m.mae_trains_per_hour} / h` : '—'}
              sub={m.baseline_mae_hourly_average != null ? `vs ${m.baseline_mae_hourly_average} for an hourly average` : 'mean absolute error'} />
            <Tile label="Daily total error" value={m.daily_total_error_pct != null ? `${m.daily_total_error_pct}%` : '—'} sub={`back-test on last ${m.holdout_days ?? '—'} days`} />
          </div>
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
            <div>
              <div className="text-xs font-semibold text-slate-500 mb-1">Average trains per hour — {corridorName(corridor)}</div>
              <div className="h-64">
                <Bar data={stacked} options={{ ...baseOptions, scales: { x: { stacked: true, grid: { display: false }, ticks: { font: { size: 9 } } }, y: { ...trainsAxis, stacked: true } } }} />
              </div>
            </div>
            <div>
              <div className="text-xs font-semibold text-slate-500 mb-1">Trains per day</div>
              <div className="h-64">
                <Line data={line} options={{ ...baseOptions, interaction: { mode: 'index', intersect: false }, scales: { x: { grid: { display: false } }, y: trainsAxis } }} />
              </div>
            </div>
          </div>
          <div className="mt-4 overflow-x-auto max-h-64 overflow-y-auto scrollbar-thin">
            <table className="w-full text-xs">
              <thead className="bg-slate-50 text-slate-600 sticky top-0">
                <tr>
                  <th className="text-left px-3 py-1.5">Window</th>
                  <th className="text-left px-3 py-1.5">Type</th>
                  <th className="text-right px-3 py-1.5">Passenger</th>
                  <th className="text-right px-3 py-1.5">Goods</th>
                  <th className="text-left px-3 py-1.5 w-40">Disruption</th>
                  <th className="text-left px-3 py-1.5">Status</th>
                </tr>
              </thead>
              <tbody>
                {data.windows.map((w) => (
                  <tr key={w.window_id} className="border-t border-slate-100">
                    <td className="px-3 py-1.5 text-slate-700 whitespace-nowrap">{w.date} · {w.start}–{w.end}</td>
                    <td className="px-3 py-1.5 text-slate-500">{w.type === 'NIGHT_BLOCK' ? 'Night' : 'Lean period'}</td>
                    <td className="px-3 py-1.5 text-right tabular-nums">{w.pax}</td>
                    <td className="px-3 py-1.5 text-right tabular-nums">{w.goods}</td>
                    <td className="px-3 py-1.5">
                      <span className="flex items-center gap-2">
                        <span className="flex-1 h-2 bg-slate-100 rounded"><span className="block h-2 rounded bg-slate-500" style={{ width: `${(w.disruption || 0) * 100}%` }} /></span>
                        <span className="tabular-nums text-slate-600">{Number(w.disruption || 0).toFixed(2)}</span>
                      </span>
                    </td>
                    <td className="px-3 py-1.5 text-slate-500">{w.status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </Card>
  )
}

/* ------------------------------------------------------------------ what-if */
const DEFAULTS = {
  window_extension_min: 0, corridor_ids: [], cancel_corridor: '', cancel_date: '',
  parallel_gangs: 4, traffic_growth_pct: 0, extra_emergencies: 0, emergency_corridor_id: '',
  objective: 'balanced', respect_approved: true,
}

// metric key, label, which direction is better, formatter
const METRICS = [
  ['tasks_scheduled', 'Tasks scheduled', 'up', (v) => v],
  ['coverage', 'Coverage', 'up', pct],
  ['priority_weighted_coverage', 'Priority-weighted coverage', 'up', pct],
  ['critical_scheduled', 'Critical tasks scheduled', 'up', (v) => v],
  ['blocks', 'Line possessions (blocks)', 'down', (v) => v],
  ['multi_dept_blocks', 'Multi-department blocks', 'up', (v) => v],
  ['possession_minutes', 'Possession minutes', 'down', (v) => v],
  ['trains_affected', 'Trains affected (forecast)', 'down', (v) => v],
  ['disruption_score', 'Disruption score', 'down', (v) => v],
  ['avg_utilization', 'Avg. window utilization', 'up', pct],
]

function WhatIfSection() {
  const [p, setP] = useState(DEFAULTS)
  const [windows, setWindows] = useState([])
  const [result, setResult] = useState(null)
  const [running, setRunning] = useState(false)
  const [err, setErr] = useState('')
  const [name, setName] = useState('')
  const [saved, setSaved] = useState([])
  const corridorName = useCorridorNames()

  const loadSaved = useCallback(() => Planning.scenarios().then(setSaved).catch(() => {}), [])
  useEffect(() => {
    Planning.windows().then(setWindows).catch(() => {})
    loadSaved()
  }, [loadSaved])

  const corridors = useMemo(() => [...new Set(windows.map((w) => w.corridor_id))], [windows])
  const dates = useMemo(() => [...new Set(windows.map((w) => w.date))].sort(), [windows])
  const set = (k, v) => setP((prev) => ({ ...prev, [k]: v }))

  const run = async (save = false) => {
    setRunning(true); setErr('')
    const cancel = p.cancel_corridor && p.cancel_date
      ? windows.filter((w) => w.corridor_id === p.cancel_corridor && w.date === p.cancel_date).map((w) => w.id)
      : []
    try {
      const res = await Planning.simulate({
        window_extension_min: Number(p.window_extension_min),
        corridor_ids: p.corridor_ids,
        cancel_window_ids: cancel,
        parallel_gangs: Number(p.parallel_gangs),
        traffic_growth_pct: Number(p.traffic_growth_pct),
        extra_emergencies: Number(p.extra_emergencies),
        emergency_corridor_id: p.emergency_corridor_id || undefined,
        objective: p.objective,
        respect_approved: p.respect_approved,
        save,
        name: save ? name || undefined : undefined,
      })
      setResult(res)
      if (save) { setName(''); loadSaved() }
    } catch (e) {
      setErr(errorText(e, 'Simulation failed'))
    } finally {
      setRunning(false)
    }
  }

  const remove = async (id) => { await Planning.deleteScenario(id).catch(() => {}); loadSaved() }

  const byCorr = result ? [...new Set([...Object.keys(result.baseline.by_corridor || {}), ...Object.keys(result.scenario.by_corridor || {})])] : []
  const compare = {
    labels: byCorr.map((c) => corridorName(c)),
    datasets: [
      { label: 'Current settings', data: byCorr.map((c) => result?.baseline.by_corridor?.[c]?.tasks || 0), backgroundColor: BASE, borderRadius: 4, borderColor: '#fff', borderWidth: 1 },
      { label: 'Scenario', data: byCorr.map((c) => result?.scenario.by_corridor?.[c]?.tasks || 0), backgroundColor: SCEN, borderRadius: 4, borderColor: '#fff', borderWidth: 1 },
    ],
  }

  return (
    <Card
      title="What-if simulation"
      info="Runs the same CP-SAT optimizer on an in-memory copy of today's data. The live plan is never touched; a scenario is stored only if you save it (parameters and results only)."
    >
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        {/* ------------ parameters */}
        <div className="space-y-3">
          <Slider label="Extend windows by" unit="min" min={-60} max={120} step={15} value={p.window_extension_min} onChange={(v) => set('window_extension_min', v)} />
          <div>
            <div className={LABEL}>…on corridors (none selected = all)</div>
            <div className="flex flex-wrap gap-1">
              {corridors.map((c) => {
                const on = p.corridor_ids.includes(c)
                return (
                  <button key={c} onClick={() => set('corridor_ids', on ? p.corridor_ids.filter((x) => x !== c) : [...p.corridor_ids, c])}
                    className={`text-[10px] px-2 py-1 rounded-full border ${on ? 'bg-slate-800 text-white border-slate-800' : 'bg-white text-slate-600 border-slate-200'}`}>
                    {corridorName(c)}
                  </button>
                )
              })}
            </div>
          </div>
          <div>
            <div className={LABEL}>Control withdraws all windows on</div>
            <div className="grid grid-cols-2 gap-2">
              <select value={p.cancel_corridor} onChange={(e) => set('cancel_corridor', e.target.value)} className={`${SELECT} w-full min-w-0`}>
                <option value="">— corridor —</option>
                {corridors.map((c) => <option key={c} value={c}>{corridorName(c)}</option>)}
              </select>
              <select value={p.cancel_date} onChange={(e) => set('cancel_date', e.target.value)} className={`${SELECT} w-full min-w-0`}>
                <option value="">— date —</option>
                {dates.map((d) => <option key={d} value={d}>{d}</option>)}
              </select>
            </div>
          </div>
          <Slider label="Parallel gangs per block" min={1} max={8} step={1} value={p.parallel_gangs} onChange={(v) => set('parallel_gangs', v)} />
          <Slider label="Traffic growth" unit="%" min={-20} max={60} step={5} value={p.traffic_growth_pct} onChange={(v) => set('traffic_growth_pct', v)} />
          <div className="grid grid-cols-2 gap-2">
            <Slider label="Extra emergencies" min={0} max={5} step={1} value={p.extra_emergencies} onChange={(v) => set('extra_emergencies', v)} />
            <label className="block">
              <span className={LABEL}>on corridor</span>
              <select value={p.emergency_corridor_id} onChange={(e) => set('emergency_corridor_id', e.target.value)} className={`${SELECT} w-full min-w-0`}>
                <option value="">Busiest (auto)</option>
                {corridors.map((c) => <option key={c} value={c}>{corridorName(c)}</option>)}
              </select>
            </label>
          </div>
          <div>
            <div className={LABEL}>Objective</div>
            <div className="flex gap-1">
              {[['balanced', 'Balanced'], ['max_coverage', 'Max coverage'], ['min_disruption', 'Min disruption']].map(([v, l]) => (
                <button key={v} onClick={() => set('objective', v)}
                  className={`flex-1 text-[11px] px-2 py-1.5 rounded-md border ${p.objective === v ? 'bg-rail-accent text-white border-rail-accent' : 'bg-white text-slate-600 border-slate-200'}`}>{l}</button>
              ))}
            </div>
          </div>
          <label className="flex items-center gap-2 text-xs text-slate-600">
            <input type="checkbox" checked={p.respect_approved} onChange={(e) => set('respect_approved', e.target.checked)} />
            Keep approved blocks fixed
          </label>
          <div className="flex gap-2 pt-1">
            <button onClick={() => run(false)} disabled={running}
              className="flex-1 bg-rail-accent hover:bg-blue-700 disabled:opacity-60 text-white text-sm font-semibold px-3 py-2 rounded-lg flex items-center justify-center gap-2">
              {running && <span className="w-4 h-4 border-2 border-white/40 border-t-white rounded-full animate-spin" />}
              {running ? 'Solving…' : 'Run scenario'}
            </button>
            <button onClick={() => setP(DEFAULTS)} className="text-xs px-3 py-2 rounded-lg bg-slate-100 text-slate-600">Reset</button>
          </div>
          <div className="flex gap-2">
            <input value={name} onChange={(e) => setName(e.target.value)} maxLength={80} placeholder="Scenario name" className={`${SELECT} flex-1 min-w-0`} />
            <button onClick={() => run(true)} disabled={running} className="text-xs px-3 py-1.5 rounded-lg border border-slate-300 text-slate-700 hover:bg-slate-50 disabled:opacity-60 whitespace-nowrap">Run &amp; save</button>
          </div>
          {err && <div className="text-xs text-red-600">{err}</div>}
        </div>

        {/* ------------ results */}
        <div className="xl:col-span-2 space-y-4">
          {!result ? (
            <div className="h-full min-h-[12rem] rounded-xl border border-dashed border-slate-300 flex items-center justify-center text-sm text-slate-400 text-center p-6">
              Change one or more parameters and run the scenario to compare it with the current planning settings.
            </div>
          ) : (
            <>
              <table className="w-full text-sm">
                <thead className="text-xs text-slate-500">
                  <tr>
                    <th className="text-left py-1.5">Metric</th>
                    <th className="text-right py-1.5">Current settings</th>
                    <th className="text-right py-1.5">Scenario</th>
                    <th className="text-right py-1.5">Change</th>
                  </tr>
                </thead>
                <tbody>
                  {METRICS.map(([k, label, better, fmt]) => {
                    const d = result.delta[k] || 0
                    const good = d === 0 ? null : (better === 'up') === d > 0
                    return (
                      <tr key={k} className="border-t border-slate-100">
                        <td className="py-1.5 text-slate-600">{label}</td>
                        <td className="py-1.5 text-right tabular-nums">{fmt(result.baseline[k])}</td>
                        <td className="py-1.5 text-right tabular-nums font-semibold text-slate-800">{fmt(result.scenario[k])}</td>
                        <td className={`py-1.5 text-right tabular-nums font-semibold ${good == null ? 'text-slate-400' : good ? 'text-emerald-700' : 'text-red-600'}`}>
                          {d === 0 ? '—' : `${good ? '▲' : '▼'} ${d > 0 ? '+' : ''}${fmt === pct ? `${(d * 100).toFixed(1)} pts` : Math.round(d * 10) / 10}`}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
              <div className="text-[11px] text-slate-500">
                Solver: {result.scenario.solver_status} in {result.scenario.solve_time_s}s ·{' '}
                {result.scenario.unscheduled_critical.length
                  ? `Critical work left unscheduled: ${result.scenario.unscheduled_critical.join(', ')}`
                  : 'All critical work is scheduled.'}
              </div>
              <div>
                <div className="text-xs font-semibold text-slate-500 mb-1">Tasks scheduled by corridor</div>
                <div className="h-56">
                  <Bar data={compare} options={{ ...baseOptions, scales: { x: { grid: { display: false }, ticks: { font: { size: 9 } } }, y: { beginAtZero: true, grid: { color: '#f1f5f9' } } } }} />
                </div>
              </div>
            </>
          )}

          {saved.length > 0 && (
            <div>
              <div className="text-xs font-semibold text-slate-500 mb-1">Saved scenarios</div>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead className="bg-slate-50 text-slate-600">
                    <tr>
                      <th className="text-left px-2 py-1.5">Name</th>
                      <th className="text-left px-2 py-1.5">By</th>
                      <th className="text-right px-2 py-1.5">Δ tasks</th>
                      <th className="text-right px-2 py-1.5">Δ blocks</th>
                      <th className="text-right px-2 py-1.5">Δ trains affected</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {saved.map((s) => (
                      <tr key={s.id} className="border-t border-slate-100">
                        <td className="px-2 py-1.5 text-slate-700">{s.name}</td>
                        <td className="px-2 py-1.5 text-slate-500">{s.created_by}</td>
                        <td className="px-2 py-1.5 text-right tabular-nums">{signed(s.metrics?.delta?.tasks_scheduled)}</td>
                        <td className="px-2 py-1.5 text-right tabular-nums">{signed(s.metrics?.delta?.blocks)}</td>
                        <td className="px-2 py-1.5 text-right tabular-nums">{signed(s.metrics?.delta?.trains_affected)}</td>
                        <td className="px-2 py-1.5 text-right">
                          <button onClick={() => remove(s.id)} className="text-slate-400 hover:text-red-600" aria-label={`Delete ${s.name}`}>✕</button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      </div>
    </Card>
  )
}

/* ------------------------------------------------------------------ bits */
const SELECT = 'border border-slate-200 rounded-lg px-2 py-1.5 text-xs bg-white text-slate-700'
const LABEL = 'block text-[11px] font-semibold text-slate-500 mb-1'

function pct(v) { return `${Math.round((v || 0) * 1000) / 10}%` }
function signed(v) { return v == null ? '—' : `${v > 0 ? '+' : ''}${Math.round(v * 10) / 10}` }

function Card({ title, info, right, children }) {
  return (
    <section className="bg-white rounded-xl border border-slate-200 shadow-sm p-5">
      <div className="flex items-center justify-between gap-3 flex-wrap mb-4">
        <h2 className="font-bold text-slate-800 flex items-center">{title}{info && <InfoTip text={info} label={title} />}</h2>
        {right}
      </div>
      {children}
    </section>
  )
}

function Tile({ label, value, sub }) {
  return (
    <div className="bg-slate-50 rounded-lg p-3">
      <div className="text-[10px] uppercase tracking-wide text-slate-500">{label}</div>
      <div className="text-xl font-extrabold text-slate-800 tabular-nums">{value}</div>
      {sub && <div className="text-[11px] text-slate-500">{sub}</div>}
    </div>
  )
}

function Slider({ label, unit = '', min, max, step, value, onChange }) {
  return (
    <label className="block">
      <span className="flex justify-between text-[11px] font-semibold text-slate-500 mb-1">
        <span>{label}</span><span className="text-slate-800 tabular-nums">{value > 0 && unit === 'min' ? '+' : ''}{value}{unit ? ` ${unit}` : ''}</span>
      </span>
      <input type="range" min={min} max={max} step={step} value={value} onChange={(e) => onChange(Number(e.target.value))} className="w-full accent-blue-600" />
    </label>
  )
}
