import { useEffect, useState, useCallback } from 'react'
import { Doughnut, Bar } from 'react-chartjs-2'
import { Dashboard } from '../api/client'
import { baseOptions, PRIORITY_PALETTE } from '../components/charts'
import Header from '../components/Header.jsx'
import KpiCard from '../components/KpiCard.jsx'
import Welcome from '../components/Welcome.jsx'
import Stepper from '../components/Stepper.jsx'
import InjectEmergencyButton from '../components/InjectEmergencyButton.jsx'
import InfoTip from '../components/InfoTip.jsx'
import { GLOSSARY } from '../utils/domain'
import { useCountUp } from '../hooks/useCountUp'

export default function DashboardPage() {
  const [kpis, setKpis] = useState(null)
  const [prio, setPrio] = useState({})
  const [deptLoad, setDeptLoad] = useState({})
  const [completion, setCompletion] = useState({})
  const [util, setUtil] = useState([])
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    setLoading(true)
    const [k, p, u, d, c] = await Promise.all([
      Dashboard.kpis(),
      Dashboard.priorityDistribution(),
      Dashboard.blockUtilization(),
      Dashboard.departmentLoad(),
      Dashboard.completion(),
    ])
    setKpis(k); setPrio(p); setUtil(u); setDeptLoad(d); setCompletion(c)
    setLoading(false)
  }, [])
  useEffect(() => { load() }, [load])

  if (loading || !kpis) {
    return (
      <>
        <Header title="Operations Dashboard" subtitle="Maintenance planning overview" onRefresh={load} />
        <div className="p-6 text-slate-400">Loading dashboard…</div>
      </>
    )
  }

  if (!kpis.planned_blocks) {
    return (
      <>
        <Header title="Operations Dashboard" subtitle="Maintenance planning overview" onRefresh={load} />
        <div className="p-6"><Welcome onDone={load} /></div>
      </>
    )
  }

  const prioData = {
    labels: Object.keys(prio),
    datasets: [{ data: Object.values(prio), backgroundColor: Object.keys(prio).map((k) => PRIORITY_PALETTE[k]), borderWidth: 0 }],
  }
  const deptData = {
    labels: Object.keys(deptLoad),
    datasets: [{ label: 'Pending tasks', data: Object.values(deptLoad), backgroundColor: ['#0ea5e9', '#8b5cf6', '#f59e0b'], borderRadius: 4 }],
  }
  const compLabels = Object.keys(completion)
  const compData = {
    labels: compLabels,
    datasets: [{ label: 'Tasks', data: compLabels.map((k) => completion[k]), backgroundColor: '#10b981', borderRadius: 4 }],
  }
  const utilData = {
    labels: util.map((b) => b.block_ref.replace('BLK-', '')),
    datasets: [{ label: 'Utilization %', data: util.map((b) => Math.round(b.utilization * 100)), backgroundColor: util.map((b) => (b.is_multi_dept ? '#2563eb' : '#94a3b8')), borderRadius: 4 }],
  }

  return (
    <>
      <Header title="Operations Dashboard" subtitle="Maintenance planning overview — Engineering · S&T · Traction" onRefresh={load} />
      <div className="p-6 space-y-6">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div className="flex-1 min-w-[280px]"><Stepper current={3} /></div>
          <InjectEmergencyButton onDone={load} />
        </div>

        <ImpactHero kpis={kpis} />

        <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-4">
          <KpiCard label="Pending Tasks" value={kpis.pending_tasks} accent="blue" icon="🧰" />
          <KpiCard label="Critical Defects" value={kpis.critical_defects} accent="red" icon="⚠️" />
          <KpiCard label="Asset Availability" value={`${Math.round(kpis.asset_availability * 100)}%`} accent="green" icon="✅"
            info="Proxy for how much of the network is free of unresolved critical/overdue work, improved by planned coverage." />
          <KpiCard label="Planned Blocks" value={kpis.planned_blocks} accent="violet" icon="🧱" info={GLOSSARY.Possession} />
          <KpiCard label="Tasks Scheduled" value={kpis.tasks_scheduled} sub={`${Math.round(kpis.coverage_ratio * 100)}% coverage`} accent="blue" icon="🗓️" info={GLOSSARY.Coverage} />
          <KpiCard label="Blocks Saved" value={kpis.blocks_saved_vs_naive} sub="vs. manual planning" accent="amber" icon="💡" info={GLOSSARY['Blocks saved']} />
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <ChartCard title="AI Priority Distribution"><Doughnut data={prioData} options={baseOptions} /></ChartCard>
          <ChartCard title="Pending Load by Department"><Bar data={deptData} options={{ ...baseOptions, plugins: { legend: { display: false } } }} /></ChartCard>
          <ChartCard title="Maintenance Completion Status"><Bar data={compData} options={{ ...baseOptions, plugins: { legend: { display: false } } }} /></ChartCard>
        </div>

        <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-4">
          <div className="flex items-center justify-between mb-2">
            <h3 className="font-bold text-slate-700 text-sm flex items-center">Block Utilization<InfoTip text={GLOSSARY.Utilization} label="Utilization" /></h3>
            <div className="flex items-center gap-4 text-[11px] text-slate-500">
              <span className="flex items-center gap-1"><span className="w-3 h-3 rounded-sm bg-rail-accent inline-block" /> Multi-department</span>
              <span className="flex items-center gap-1"><span className="w-3 h-3 rounded-sm bg-slate-400 inline-block" /> Single-department</span>
            </div>
          </div>
          <div className="h-72"><Bar data={utilData} options={{ ...baseOptions, plugins: { legend: { display: false } }, scales: { y: { max: 100, ticks: { callback: (v) => v + '%' } } } }} /></div>
        </div>
      </div>
    </>
  )
}

function CountUp({ value, decimals = 0, suffix = '' }) {
  const v = useCountUp(value)
  return <>{v.toFixed(decimals)}{suffix}</>
}

function ImpactHero({ kpis }) {
  const naive = kpis.naive_blocks ?? (kpis.planned_blocks + kpis.blocks_saved_vs_naive)
  const optimized = kpis.optimized_blocks ?? kpis.planned_blocks
  const saved = kpis.blocks_saved_vs_naive || 0
  const pct = naive ? Math.round((saved / naive) * 100) : 0
  const maxv = Math.max(naive, optimized, 1)

  return (
    <div className="relative overflow-hidden rounded-2xl text-white p-6 shadow-lg"
      style={{ background: 'radial-gradient(1200px 200px at 100% 0%, rgba(37,99,235,0.55), transparent), linear-gradient(135deg, #0b1220 0%, #0f172a 45%, #1e3a8a 100%)' }}>
      <div className="absolute -top-16 -right-16 w-64 h-64 rounded-full bg-blue-500/10 blur-3xl pointer-events-none" />
      <div className="relative flex items-start justify-between gap-6 flex-wrap">
        <div className="min-w-[280px] flex-1">
          <div className="text-[11px] uppercase tracking-[0.2em] text-blue-200/80 font-semibold">Planning impact</div>
          <div className="mt-2 flex items-baseline gap-3 flex-wrap">
            <span className="text-5xl font-black leading-none tabular-nums"><CountUp value={saved} /></span>
            <span className="text-lg font-semibold text-blue-100/90">line possessions avoided{pct ? ` · ${pct}% fewer` : ''}</span>
          </div>
          <p className="text-sm text-blue-100/70 mt-2 max-w-xl">
            The AI optimizer coordinated corridors and combined multi-department work, cutting the plan from
            <span className="font-semibold text-white"> {naive} manual possessions</span> to
            <span className="font-semibold text-white"> {optimized} shared blocks</span> — scheduling {Math.round((kpis.coverage_ratio || 0) * 100)}% of block-requiring work.
          </p>

          {/* before / after comparison */}
          <div className="mt-4 space-y-2 max-w-md">
            <BarRow label="Manual planning" pct={(naive / maxv) * 100} valueLabel={`${naive}`} track="bg-white/10" fill="bg-white/30" />
            <BarRow label="AI-optimized" pct={(optimized / maxv) * 100} valueLabel={`${optimized}`} track="bg-white/10" fill="bg-gradient-to-r from-emerald-400 to-teal-400" />
          </div>
        </div>

        <div className="grid grid-cols-3 gap-3">
          <HeroStat value={<CountUp value={optimized} />} label="optimized blocks" />
          <HeroStat value={<CountUp value={kpis.multi_dept_blocks} />} label="multi-dept blocks" />
          <HeroStat value={<CountUp value={Math.round((kpis.avg_block_utilization || 0) * 100)} suffix="%" />} label="avg utilization" />
        </div>
      </div>
    </div>
  )
}

function BarRow({ label, pct, valueLabel, track, fill }) {
  return (
    <div className="flex items-center gap-3">
      <div className="w-28 shrink-0 text-[11px] text-blue-100/80">{label}</div>
      <div className={`relative flex-1 h-4 rounded-full ${track} overflow-hidden`}>
        <div className={`h-full rounded-full ${fill} transition-all duration-700`} style={{ width: `${Math.max(6, pct)}%` }} />
      </div>
      <div className="w-8 text-right text-xs font-bold tabular-nums">{valueLabel}</div>
    </div>
  )
}

function HeroStat({ value, label }) {
  return (
    <div className="bg-white/10 backdrop-blur-sm rounded-xl px-4 py-3 text-center min-w-[96px] border border-white/10">
      <div className="text-3xl font-black leading-none tabular-nums">{value}</div>
      <div className="text-[10px] text-blue-100/80 mt-1.5 uppercase tracking-wide">{label}</div>
    </div>
  )
}

function ChartCard({ title, children }) {
  return (
    <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-4">
      <h3 className="font-bold text-slate-700 mb-2 text-sm">{title}</h3>
      <div className="h-56">{children}</div>
    </div>
  )
}
