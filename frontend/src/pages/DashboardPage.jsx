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

  // First-run: no plan yet -> guide the user to generate one.
  if (!kpis.planned_blocks) {
    return (
      <>
        <Header title="Operations Dashboard" subtitle="Maintenance planning overview" onRefresh={load} />
        <div className="p-6">
          <Welcome onDone={load} />
        </div>
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
        <Stepper current={3} />
        <div className="flex justify-end"><InjectEmergencyButton onDone={load} /></div>

        {/* Impact hero — the headline result of the optimizer */}
        <ImpactHero kpis={kpis} />

        {/* KPI cards */}
        <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-4">
          <KpiCard label="Pending Tasks" value={kpis.pending_tasks} accent="blue" icon="🧰" />
          <KpiCard label="Critical Defects" value={kpis.critical_defects} accent="red" icon="⚠️" />
          <KpiCard label="Asset Availability" value={`${Math.round(kpis.asset_availability * 100)}%`} accent="green" icon="✅"
            info="Proxy for how much of the network is free of unresolved critical/overdue work, improved by planned coverage." />
          <KpiCard label="Planned Blocks" value={kpis.planned_blocks} accent="violet" icon="🧱"
            info={GLOSSARY.Possession} />
          <KpiCard label="Tasks Scheduled" value={kpis.tasks_scheduled} sub={`${Math.round(kpis.coverage_ratio * 100)}% coverage`} accent="blue" icon="🗓️"
            info={GLOSSARY.Coverage} />
          <KpiCard label="Blocks Saved" value={kpis.blocks_saved_vs_naive} sub="vs. manual planning" accent="amber" icon="💡"
            info={GLOSSARY['Blocks saved']} />
        </div>

        {/* Charts row */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <ChartCard title="AI Priority Distribution">
            <Doughnut data={prioData} options={baseOptions} />
          </ChartCard>
          <ChartCard title="Pending Load by Department">
            <Bar data={deptData} options={{ ...baseOptions, plugins: { legend: { display: false } } }} />
          </ChartCard>
          <ChartCard title="Maintenance Completion Status">
            <Bar data={compData} options={{ ...baseOptions, plugins: { legend: { display: false } } }} />
          </ChartCard>
        </div>

        {/* Block utilization */}
        <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-4">
          <div className="flex items-center justify-between mb-2">
            <h3 className="font-bold text-slate-700 text-sm flex items-center">
              Block Utilization
              <InfoTip text={GLOSSARY.Utilization} label="Utilization" />
            </h3>
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

function ImpactHero({ kpis }) {
  const naive = kpis.naive_blocks ?? (kpis.planned_blocks + kpis.blocks_saved_vs_naive)
  const optimized = kpis.optimized_blocks ?? kpis.planned_blocks
  const saved = kpis.blocks_saved_vs_naive || 0
  const pct = naive ? Math.round((saved / naive) * 100) : 0
  return (
    <div className="rounded-2xl bg-gradient-to-br from-rail-navy to-rail-blue text-white p-5 shadow-sm">
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <div className="text-xs uppercase tracking-wide text-blue-200/80 font-semibold">Planning impact</div>
          <div className="text-2xl font-extrabold mt-1">
            {optimized} optimized blocks <span className="text-blue-200/70 font-semibold text-lg">vs. {naive} manual possessions</span>
          </div>
          <p className="text-sm text-blue-100/80 mt-1">
            The optimizer combined multi-department work and coordinated corridors to avoid{' '}
            <span className="font-bold text-white">{saved} line possession{saved === 1 ? '' : 's'}</span>
            {pct ? ` (${pct}% fewer)` : ''}, scheduling {Math.round((kpis.coverage_ratio || 0) * 100)}% of block-requiring work.
          </p>
        </div>
        <div className="flex gap-3">
          <HeroStat v={saved} l="possessions avoided" />
          <HeroStat v={kpis.multi_dept_blocks} l="multi-dept blocks" />
          <HeroStat v={`${Math.round((kpis.avg_block_utilization || 0) * 100)}%`} l="avg utilization" />
        </div>
      </div>
    </div>
  )
}

function HeroStat({ v, l }) {
  return (
    <div className="bg-white/10 rounded-xl px-4 py-2 text-center min-w-[92px]">
      <div className="text-2xl font-extrabold leading-none">{v}</div>
      <div className="text-[10px] text-blue-100/80 mt-1">{l}</div>
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
