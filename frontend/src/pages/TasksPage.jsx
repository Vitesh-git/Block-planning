import { Fragment, useEffect, useState, useCallback, useMemo } from 'react'
import { Tasks } from '../api/client'
import Header from '../components/Header.jsx'
import PriorityBadge, { DeptBadge } from '../components/PriorityBadge.jsx'
import InfoTip from '../components/InfoTip.jsx'
import { useCorridorNames } from '../hooks/useCorridorNames'

const PRIORITIES = ['Critical', 'High', 'Medium', 'Low']
const STATUS_LABEL = { PENDING: 'Pending', IN_PROGRESS: 'In progress', COMPLETED: 'Completed' }

// Prioritized task list with AI explanations + controller actions.
export default function TasksPage() {
  const [tasks, setTasks] = useState([])
  const [filters, setFilters] = useState({ department: '', priority: '', status: 'PENDING' })
  const [search, setSearch] = useState('')
  const [expanded, setExpanded] = useState(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(null)
  const corridorName = useCorridorNames()

  const load = useCallback(async () => {
    setLoading(true)
    const params = Object.fromEntries(Object.entries(filters).filter(([, v]) => v))
    const data = await Tasks.list({ ...params, limit: 400 })
    setTasks(data)
    setLoading(false)
  }, [filters])
  useEffect(() => { load() }, [load])

  const act = async (id, body) => {
    setBusy(id)
    try {
      const updated = await Tasks.update(id, body)
      setTasks((prev) => prev.map((t) => (t.id === id ? { ...t, ...updated } : t)))
    } catch (e) {
      alert(e?.response?.data?.detail || 'Update failed')
    } finally {
      setBusy(null)
    }
  }

  const visible = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return tasks
    return tasks.filter((t) =>
      [t.source_id, t.description, t.station_code, t.defect_code, corridorName(t.corridor_id)]
        .filter(Boolean)
        .some((v) => String(v).toLowerCase().includes(q))
    )
  }, [tasks, search, corridorName])

  return (
    <>
      <Header title="AI-Prioritized Tasks" subtitle="Explainable Priority Engine — review, act, and override" onRefresh={load} />
      <div className="p-6 space-y-4">
        <div className="flex gap-3 flex-wrap items-center">
          <input value={search} onChange={(e) => setSearch(e.target.value)}
            placeholder="Search ID, station, defect, corridor…"
            className="border border-slate-200 rounded-lg px-3 py-1.5 text-sm bg-white text-slate-700 w-64 max-w-full" />
          <Select label="Department" value={filters.department} onChange={(v) => setFilters((f) => ({ ...f, department: v }))}
            options={[['', 'All'], ['ENG', 'Engineering (P.Way)'], ['SNT', 'Signal & Telecom'], ['TRD', 'Traction (OHE)']]} />
          <Select label="Priority" value={filters.priority} onChange={(v) => setFilters((f) => ({ ...f, priority: v }))}
            options={[['', 'All'], ...PRIORITIES.map((p) => [p, p])]} />
          <Select label="Status" value={filters.status} onChange={(v) => setFilters((f) => ({ ...f, status: v }))}
            options={[['', 'All'], ['PENDING', 'Pending'], ['IN_PROGRESS', 'In progress'], ['COMPLETED', 'Completed']]} />
          <span className="text-xs text-slate-500 ml-auto">{visible.length} of {tasks.length} tasks</span>
        </div>

        <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-slate-600 text-xs">
                <tr>
                  <th className="text-left px-4 py-2">Source ID</th>
                  <th className="text-left px-4 py-2">Priority</th>
                  <th className="text-left px-4 py-2">Dept</th>
                  <th className="text-left px-4 py-2">Corridor</th>
                  <th className="text-center px-4 py-2">Sev</th>
                  <th className="text-center px-4 py-2">Overdue</th>
                  <th className="text-left px-4 py-2">Status</th>
                  <th className="text-right px-4 py-2">
                    <InfoTip text="0–1 AI priority score used by the optimizer to weight what gets scheduled first." label="Score">Score</InfoTip>
                  </th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr><td colSpan="8" className="px-4 py-6 text-slate-400">Loading…</td></tr>
                ) : visible.length === 0 ? (
                  <tr><td colSpan="8" className="px-4 py-10 text-center text-slate-400">
                    {tasks.length === 0
                      ? 'No tasks yet — click Run AI Planner above to load and prioritize maintenance tasks.'
                      : 'No tasks match your search or filters.'}
                  </td></tr>
                ) : visible.map((t) => (
                  <Fragment key={t.id}>
                    <tr onClick={() => setExpanded(expanded === t.id ? null : t.id)}
                      className="border-t border-slate-100 cursor-pointer hover:bg-blue-50">
                      <td className="px-4 py-2 font-medium text-slate-700">{t.source_id}</td>
                      <td className="px-4 py-2"><PriorityBadge label={t.priority_label} /></td>
                      <td className="px-4 py-2"><DeptBadge dept={t.department} /></td>
                      <td className="px-4 py-2 text-slate-500 max-w-[11rem] truncate" title={corridorName(t.corridor_id)}>{corridorName(t.corridor_id)}</td>
                      <td className="px-4 py-2 text-center">{t.severity}</td>
                      <td className={`px-4 py-2 text-center ${t.overdue_days > 0 ? 'text-red-600 font-semibold' : 'text-slate-400'}`}>{t.overdue_days}d</td>
                      <td className="px-4 py-2"><StatusPill status={t.status} /></td>
                      <td className="px-4 py-2 text-right font-mono text-slate-600">{t.priority_score.toFixed(2)}</td>
                    </tr>
                    {expanded === t.id && (
                      <tr className="bg-blue-50/50">
                        <td colSpan="8" className="px-4 py-3">
                          <div className="text-xs text-slate-600">
                            <span className="font-semibold text-slate-700">🧠 Why {t.priority_label}: </span>
                            {t.priority_explanation}
                          </div>
                          <div className="text-[11px] text-slate-500 mt-1">
                            {t.description} · {t.station_code} @ {t.km_post.toFixed(1)} km ·
                            asset criticality {t.asset_criticality}/5 · est. {t.estimated_duration_min} min ·
                            {t.requires_traffic_block ? ' needs traffic block' : ' no block required'}
                          </div>

                          {/* Controller actions */}
                          <div className="mt-3 flex flex-wrap items-center gap-2" onClick={(e) => e.stopPropagation()}>
                            <span className="text-[11px] font-semibold text-slate-500">Status:</span>
                            {['PENDING', 'IN_PROGRESS', 'COMPLETED'].map((s) => (
                              <button key={s} disabled={busy === t.id || t.status === s}
                                onClick={() => act(t.id, { status: s })}
                                className={`text-[11px] px-2 py-1 rounded-md border font-medium ${t.status === s ? 'bg-slate-800 text-white border-slate-800' : 'bg-white text-slate-600 border-slate-200 hover:bg-slate-50'} disabled:opacity-60`}>
                                {STATUS_LABEL[s]}
                              </button>
                            ))}
                            <span className="w-px h-5 bg-slate-200 mx-1" />
                            <span className="text-[11px] font-semibold text-slate-500">Override priority:</span>
                            <select value={t.priority_label} disabled={busy === t.id}
                              onChange={(e) => act(t.id, { priority_label: e.target.value })}
                              className="text-[11px] border border-slate-200 rounded-md px-2 py-1 bg-white text-slate-700">
                              {PRIORITIES.map((p) => <option key={p} value={p}>{p}</option>)}
                            </select>
                            {busy === t.id && <span className="text-[11px] text-slate-400">saving…</span>}
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        </div>
        <p className="text-[11px] text-slate-400">Click any row to expand — see the model's reason and change status or override the priority.</p>
      </div>
    </>
  )
}

function StatusPill({ status }) {
  const s = {
    PENDING: 'bg-slate-100 text-slate-600',
    IN_PROGRESS: 'bg-blue-100 text-blue-700',
    COMPLETED: 'bg-emerald-100 text-emerald-700',
  }[status] || 'bg-slate-100 text-slate-600'
  return <span className={`inline-flex px-2 py-0.5 rounded-full text-[10px] font-semibold ${s}`}>{STATUS_LABEL[status] || status}</span>
}

function Select({ label, value, onChange, options }) {
  return (
    <label className="text-xs text-slate-500 flex items-center gap-1.5">
      {label}
      <select value={value} onChange={(e) => onChange(e.target.value)}
        className="border border-slate-200 rounded-lg px-2 py-1.5 text-sm bg-white text-slate-700">
        {options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
      </select>
    </label>
  )
}
