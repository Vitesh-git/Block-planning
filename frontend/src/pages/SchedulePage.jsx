import { useEffect, useState, useCallback } from 'react'
import { Blocks, Dashboard, Planning, errorText } from '../api/client'
import Header from '../components/Header.jsx'
import PriorityBadge, { DeptBadge } from '../components/PriorityBadge.jsx'
import GanttSchedule from '../components/GanttSchedule.jsx'
import InfoTip from '../components/InfoTip.jsx'
import ApprovalBadge from '../components/ApprovalBadge.jsx'
import RescheduleControl from '../components/RescheduleControl.jsx'
import { useCorridorNames } from '../hooks/useCorridorNames'
import { GLOSSARY, dept } from '../utils/domain'

export default function SchedulePage() {
  const [blocks, setBlocks] = useState([])
  const [calendar, setCalendar] = useState({})
  const [unscheduled, setUnscheduled] = useState([])
  const [range, setRange] = useState('weekly')
  const [mode, setMode] = useState('timeline')
  const [selected, setSelected] = useState(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [showUnsched, setShowUnsched] = useState(false)
  const [versions, setVersions] = useState([])
  const [showVersions, setShowVersions] = useState(false)
  const [note, setNote] = useState('')
  const [err, setErr] = useState('')
  const [audit, setAudit] = useState([])
  const [confirmAll, setConfirmAll] = useState(false)
  const corridorName = useCorridorNames()

  const load = useCallback(async () => {
    setLoading(true)
    const [b, c, u, v] = await Promise.all([
      Blocks.list(), Dashboard.calendar(), Blocks.unscheduled(), Planning.versions(15).catch(() => []),
    ])
    setBlocks(b); setCalendar(c); setUnscheduled(u); setVersions(v)
    setSelected((prev) => b.find((x) => x.id === prev?.id) || b[0] || null)
    setLoading(false)
  }, [])
  useEffect(() => { load() }, [load])

  // Decision history of the selected block (audit trail).
  useEffect(() => {
    setNote(''); setErr('')
    if (!selected?.block_ref) { setAudit([]); return }
    Planning.audit({ entity_type: 'BLOCK', entity_id: selected.block_ref, limit: 20 }).then(setAudit).catch(() => setAudit([]))
  }, [selected?.block_ref, selected?.approval_status])

  const approve = async (id, status) => {
    if (status === 'REJECTED' && note.trim().length < 5) { setErr('Give a reason for the rejection (at least 5 characters).'); return }
    setBusy(true); setErr('')
    try {
      const updated = await Blocks.update(id, { approval_status: status, note: note.trim() || undefined })
      setBlocks((prev) => prev.map((b) => (b.id === id ? { ...b, ...updated } : b)))
      setSelected((prev) => (prev?.id === id ? { ...prev, ...updated } : prev))
    } catch (e) {
      setErr(errorText(e, 'Update failed'))
    } finally {
      setBusy(false)
    }
  }

  const approveAll = async () => {
    if (!confirmAll) { setConfirmAll(true); return }
    setConfirmAll(false); setBusy(true)
    try { await Blocks.approveAll(); await load() } catch (e) { setErr(errorText(e)) } finally { setBusy(false) }
  }

  const dates = Object.keys(calendar).sort()
  const shownDates = range === 'weekly' ? dates.slice(0, 7) : dates
  const shownSet = new Set(shownDates)
  const shownBlocks = blocks.filter((b) => shownSet.has(b.date))
  const approvalByRef = Object.fromEntries(blocks.map((b) => [b.block_ref, b.approval_status]))
  const approvedCount = blocks.filter((b) => b.approval_status === 'APPROVED').length
  const pendingCount = blocks.filter((b) => b.approval_status === 'PENDING').length
  const latest = versions[0]
  const empty = !loading && blocks.length === 0

  return (
    <>
      <Header title="AI-Generated Maintenance Schedule" subtitle="OR-Tools optimized block plan — coordinated across Engineering, S&T and Traction" onRefresh={load} />
      <div className="p-6 space-y-6">
        <div className="flex items-center gap-2 flex-wrap">
          {['weekly', 'monthly'].map((v) => (
            <button key={v} onClick={() => setRange(v)}
              className={`px-3 py-1.5 rounded-lg text-sm font-semibold capitalize ${range === v ? 'bg-rail-accent text-white' : 'bg-white text-slate-600 border border-slate-200'}`}>
              {v}
            </button>
          ))}
          <span className="w-px h-6 bg-slate-200 mx-1" />
          {[['calendar', '🗓️ Calendar'], ['timeline', '📊 Timeline']].map(([v, l]) => (
            <button key={v} onClick={() => setMode(v)}
              className={`px-3 py-1.5 rounded-lg text-sm font-semibold ${mode === v ? 'bg-slate-800 text-white' : 'bg-white text-slate-600 border border-slate-200'}`}>
              {l}
            </button>
          ))}
          <span className="text-xs text-slate-500 ml-1">{shownBlocks.length} blocks · {approvedCount} approved</span>
          {latest && (
            <button onClick={() => setShowVersions(true)} title="Plan version history"
              className="text-[11px] font-semibold bg-slate-800 text-white rounded-full px-2 py-0.5">
              Plan v{latest.version} · {TRIGGER[latest.trigger_event] || latest.trigger_event}
            </button>
          )}
          {pendingCount > 0 && (
            <button onClick={approveAll} onBlur={() => setConfirmAll(false)} disabled={busy}
              className={`text-xs font-semibold px-2.5 py-1.5 rounded-lg border ${confirmAll ? 'bg-emerald-600 text-white border-emerald-600' : 'bg-white text-emerald-700 border-emerald-300 hover:bg-emerald-50'}`}>
              {confirmAll ? `Confirm: approve ${pendingCount}` : `✓ Approve all pending (${pendingCount})`}
            </button>
          )}
          <div className="ml-auto"><RescheduleControl onDone={load} /></div>
        </div>

        {loading ? (
          <div className="text-slate-400">Loading schedule…</div>
        ) : empty ? (
          <EmptyState />
        ) : (
          <>
            {mode === 'timeline' ? (
              <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-4 overflow-x-auto">
                <DeptLegend />
                <GanttSchedule blocks={shownBlocks} corridorName={corridorName} selected={selected} onSelect={setSelected} />
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3">
                {shownDates.map((d) => (
                  <div key={d} className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
                    <div className="bg-rail-navy text-white px-3 py-2 text-xs font-bold">
                      {new Date(d).toLocaleDateString('en-IN', { weekday: 'short', day: '2-digit', month: 'short' })}
                      <span className="float-right text-slate-300 font-normal">{calendar[d].length} blocks</span>
                    </div>
                    <div className="p-2 space-y-2 max-h-64 overflow-y-auto scrollbar-thin">
                      {calendar[d].map((blk) => (
                        <div key={blk.block_ref} className={`rounded-lg p-2 text-xs border ${blk.is_multi_dept ? 'border-rail-accent/40 bg-blue-50' : 'border-slate-200 bg-slate-50'}`}>
                          <div className="flex justify-between gap-1">
                            <span className="font-semibold text-slate-700 truncate" title={corridorName(blk.corridor_id)}>{corridorName(blk.corridor_id)}</span>
                            <span className="text-slate-500 whitespace-nowrap">{blk.start_time}–{blk.end_time}</span>
                          </div>
                          <div className="mt-1 flex items-center gap-1 flex-wrap">
                            {blk.departments.split(',').map((dp) => <DeptBadge key={dp} dept={dp} />)}
                            {approvalByRef[blk.block_ref] && approvalByRef[blk.block_ref] !== 'PENDING' && (
                              <ApprovalBadge status={approvalByRef[blk.block_ref]} />
                            )}
                          </div>
                          <div className="mt-1 text-[11px] text-slate-500">{blk.task_count} tasks · {Math.round(blk.utilization * 100)}% used</div>
                        </div>
                      ))}
                      {calendar[d].length === 0 && <div className="text-[11px] text-slate-400 p-2">No blocks</div>}
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Detailed block table + selected detail */}
            <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
              <div className="xl:col-span-2 bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
                <div className="px-4 py-3 border-b border-slate-200 font-bold text-slate-700 text-sm">Block Schedule</div>
                <div className="overflow-x-auto max-h-[28rem] overflow-y-auto scrollbar-thin">
                  <table className="w-full text-sm">
                    <thead className="bg-slate-50 text-slate-600 text-xs sticky top-0">
                      <tr>
                        <th className="text-left px-4 py-2">Block</th>
                        <th className="text-left px-4 py-2">Date</th>
                        <th className="text-left px-4 py-2">Corridor</th>
                        <th className="text-left px-4 py-2">Window</th>
                        <th className="text-left px-4 py-2">Depts</th>
                        <th className="text-right px-4 py-2">Tasks</th>
                        <th className="text-left px-4 py-2">Sanction</th>
                      </tr>
                    </thead>
                    <tbody>
                      {shownBlocks.map((b) => (
                        <tr key={b.id} onClick={() => setSelected(b)}
                          className={`border-t border-slate-100 cursor-pointer hover:bg-blue-50 ${selected?.id === b.id ? 'bg-blue-50' : ''}`}>
                          <td className="px-4 py-2 font-medium text-slate-700">{b.block_ref}</td>
                          <td className="px-4 py-2 text-slate-500">{b.date}</td>
                          <td className="px-4 py-2 text-slate-600 max-w-[11rem] truncate" title={corridorName(b.corridor_id)}>{corridorName(b.corridor_id)}</td>
                          <td className="px-4 py-2 text-slate-500 whitespace-nowrap">{b.start_time}–{b.end_time}</td>
                          <td className="px-4 py-2"><div className="flex gap-1 flex-wrap">{b.departments.split(',').map((dp) => <DeptBadge key={dp} dept={dp} />)}</div></td>
                          <td className="px-4 py-2 text-right">{b.task_count}</td>
                          <td className="px-4 py-2"><ApprovalBadge status={b.approval_status} /></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-4">
                <h3 className="font-bold text-slate-700 text-sm mb-3">Block Detail</h3>
                {selected ? (
                  <>
                    <div className="flex items-center justify-between gap-2">
                      <div className="text-lg font-extrabold text-slate-800">{selected.block_ref}</div>
                      <ApprovalBadge status={selected.approval_status} />
                    </div>
                    <div className="text-xs text-slate-500 mb-3">
                      {corridorName(selected.corridor_id)} · {selected.date} · {selected.start_time}–{selected.end_time}
                    </div>

                    {selected.approval_status !== 'PENDING' && selected.approved_by && (
                      <div className="text-[11px] text-slate-500 mb-2">
                        {selected.approval_status === 'APPROVED' ? 'Approved' : 'Rejected'} by <span className="font-semibold text-slate-700">{selected.approved_by}</span>
                        {selected.approved_at && ` · ${new Date(selected.approved_at + 'Z').toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' })}`}
                        {selected.approval_note && <div className="italic">“{selected.approval_note}”</div>}
                      </div>
                    )}

                    {/* Sanction controls */}
                    <input value={note} onChange={(e) => setNote(e.target.value)} maxLength={1000}
                      placeholder="Note / reason (required to reject)"
                      className="w-full mb-2 border border-slate-200 rounded-md px-2 py-1.5 text-xs text-slate-700" />
                    {err && <div className="text-[11px] text-red-600 mb-2">{err}</div>}
                    <div className="flex items-center gap-2 mb-3">
                      <button disabled={busy || selected.approval_status === 'APPROVED'} onClick={() => approve(selected.id, 'APPROVED')}
                        className="flex-1 text-xs font-semibold px-2 py-1.5 rounded-md bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white">✓ Approve</button>
                      <button disabled={busy || selected.approval_status === 'REJECTED'} onClick={() => approve(selected.id, 'REJECTED')}
                        className="flex-1 text-xs font-semibold px-2 py-1.5 rounded-md bg-red-600 hover:bg-red-700 disabled:opacity-50 text-white">✕ Reject</button>
                      <button disabled={busy || selected.approval_status === 'PENDING'} onClick={() => approve(selected.id, 'PENDING')}
                        className="text-xs font-semibold px-2 py-1.5 rounded-md bg-slate-100 hover:bg-slate-200 disabled:opacity-50 text-slate-600">Reset</button>
                    </div>

                    <div className="grid grid-cols-2 gap-2 text-xs mb-3">
                      <Stat label="Planned" value={`${selected.planned_minutes} min`} />
                      <Stat label="Window" value={`${selected.window_minutes} min`} />
                      <Stat label={<InfoTip text={GLOSSARY.Utilization} label="Utilization">Utilization</InfoTip>} value={`${Math.round(selected.utilization * 100)}%`} />
                      <Stat label={<InfoTip text={GLOSSARY.Disruption} label="Disruption">Disruption</InfoTip>} value={selected.disruption_score} />
                    </div>
                    <BlockWhy ex={selected.explanation} />
                    <div className="text-xs font-semibold text-slate-500 mb-1">Tasks in block</div>
                    <div className="space-y-2 max-h-64 overflow-y-auto scrollbar-thin">
                      {selected.tasks.map((t) => (
                        <div key={t.task_id} className="border border-slate-100 rounded-lg p-2">
                          <div className="flex justify-between items-center">
                            <span className="font-medium text-slate-700 text-xs">{t.source_id}</span>
                            <PriorityBadge label={t.priority_label} />
                          </div>
                          <div className="text-[11px] text-slate-500 mt-0.5">{t.description}</div>
                          <div className="mt-1 flex items-center gap-2 text-[10px] text-slate-400">
                            <DeptBadge dept={t.department} /> {t.station_code} · {t.estimated_duration_min} min
                          </div>
                        </div>
                      ))}
                    </div>
                    {audit.length > 0 && (
                      <div className="mt-3">
                        <div className="text-xs font-semibold text-slate-500 mb-1">Decision history</div>
                        <ul className="space-y-1 text-[11px] text-slate-600">
                          {audit.map((a) => (
                            <li key={a.id}><span className="font-semibold">{a.action}</span> by {a.actor} · {fmtTime(a.created_at)}{a.note ? ` — ${a.note}` : ''}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </>
                ) : (
                  <div className="text-slate-400 text-sm">Select a block to see details.</div>
                )}
              </div>
            </div>

            {/* Unscheduled work panel */}
            <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
              <button onClick={() => setShowUnsched((v) => !v)} className="w-full flex items-center justify-between px-4 py-3 text-left">
                <span className="font-bold text-slate-700 text-sm flex items-center gap-2">
                  ⚠️ Unscheduled work
                  <span className="text-[11px] font-semibold bg-amber-100 text-amber-700 rounded-full px-2 py-0.5">{unscheduled.length}</span>
                </span>
                <span className="text-slate-400 text-sm">{showUnsched ? '▲ hide' : '▼ show why'}</span>
              </button>
              {showUnsched && (
                <div className="border-t border-slate-100 overflow-x-auto max-h-80 overflow-y-auto scrollbar-thin">
                  {unscheduled.length === 0 ? (
                    <div className="px-4 py-6 text-sm text-emerald-700">🎉 Every block-requiring task was scheduled.</div>
                  ) : (
                    <table className="w-full text-sm">
                      <thead className="bg-slate-50 text-slate-600 text-xs sticky top-0">
                        <tr>
                          <th className="text-left px-4 py-2">Task</th>
                          <th className="text-left px-4 py-2">Dept</th>
                          <th className="text-left px-4 py-2">Corridor</th>
                          <th className="text-left px-4 py-2">Priority</th>
                          <th className="text-left px-4 py-2">Why it couldn't be scheduled</th>
                        </tr>
                      </thead>
                      <tbody>
                        {unscheduled.map((u) => (
                          <tr key={u.id} className="border-t border-slate-100">
                            <td className="px-4 py-2 font-medium text-slate-700">{u.source_id}</td>
                            <td className="px-4 py-2"><DeptBadge dept={u.department} /></td>
                            <td className="px-4 py-2 text-slate-500 max-w-[10rem] truncate" title={corridorName(u.corridor_id)}>{corridorName(u.corridor_id)}</td>
                            <td className="px-4 py-2"><PriorityBadge label={u.priority_label} /></td>
                            <td className="px-4 py-2 text-slate-600">{u.reason}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              )}
            </div>
            {showVersions && <VersionHistory versions={versions} onClose={() => setShowVersions(false)} />}
          </>
        )}
      </div>
    </>
  )
}

const TRIGGER = {
  FULL_PLAN: 'Full plan', EMERGENCY_DEFECT: 'Emergency defect', WINDOW_CANCELLED: 'Window cancelled',
  WINDOW_REDUCED: 'Window shortened', TASK_COMPLETED: 'Task completed', REPLAN: 'Re-plan',
}
const fmtTime = (iso) => (iso ? new Date(iso + 'Z').toLocaleString('en-IN', { dateStyle: 'short', timeStyle: 'short' }) : '')

// "Why this block" — structured explanation stored by the optimizer.
function BlockWhy({ ex }) {
  if (!ex || !ex.summary) return null
  const t = ex.traffic || {}
  return (
    <div className="mb-3 rounded-lg border border-blue-100 bg-blue-50/50 p-2.5">
      <div className="text-xs font-semibold text-slate-700 mb-1">🧠 Why this block</div>
      <div className="text-[11px] text-slate-600 mb-1.5">{ex.summary}</div>
      {t.source === 'forecast' && (
        <div className="flex gap-1.5 flex-wrap mb-1.5 text-[10px] font-semibold">
          <span className="rounded-full px-2 py-0.5 bg-white border border-slate-200 text-slate-700">🚆 {Math.round(t.pax)} passenger</span>
          <span className="rounded-full px-2 py-0.5 bg-white border border-slate-200 text-slate-700">🚚 {Math.round(t.goods)} goods</span>
          <span className="rounded-full px-2 py-0.5 bg-white border border-slate-200 text-slate-700">disruption {Number(t.disruption).toFixed(2)}</span>
        </div>
      )}
      <ul className="list-disc pl-4 space-y-0.5 text-[11px] text-slate-600">
        {(ex.reasons || []).map((r) => <li key={r}>{r}</li>)}
      </ul>
    </div>
  )
}

// Plan version history (dynamic rescheduling audit).
function VersionHistory({ versions, onClose }) {
  return (
    <div className="fixed inset-0 z-[700] bg-slate-900/30 flex justify-end" onClick={onClose}>
      <div className="w-full max-w-md h-full bg-white shadow-xl p-5 overflow-y-auto" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-bold text-slate-800">Plan version history</h3>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-700 text-xl leading-none" aria-label="Close">×</button>
        </div>
        <ol className="space-y-3">
          {versions.map((v) => (
            <li key={v.version} className="border border-slate-200 rounded-lg p-3">
              <div className="flex items-center justify-between">
                <span className="font-bold text-slate-800 text-sm">v{v.version} · {TRIGGER[v.trigger_event] || v.trigger_event}</span>
                <span className="text-[10px] text-slate-400">{fmtTime(v.changed_at)}</span>
              </div>
              <div className="text-[11px] text-slate-500 mt-0.5">by {v.changed_by}{v.change_reason ? ` — ${v.change_reason}` : ''}</div>
              <div className="mt-2 grid grid-cols-4 gap-1 text-center text-[10px]">
                <Diff n={v.diff?.added} l="added" />
                <Diff n={v.diff?.moved} l="moved" />
                <Diff n={v.diff?.dropped} l="dropped" />
                <Diff n={v.diff?.unchanged} l="unchanged" />
              </div>
              <div className="text-[10px] text-slate-400 mt-2">
                {v.blocks} blocks · {v.tasks_scheduled} tasks · {v.solver_status} in {v.solve_time_s}s · {v.num_variables} vars / {v.num_constraints} constraints
              </div>
            </li>
          ))}
        </ol>
      </div>
    </div>
  )
}

function Diff({ n, l }) {
  return (
    <div className="bg-slate-50 rounded px-1 py-1">
      <div className="font-bold text-slate-700 text-xs">{n ?? 0}</div>
      <div className="text-slate-400">{l}</div>
    </div>
  )
}

function DeptLegend() {
  const items = ['ENG', 'SNT', 'TRD']
  return (
    <div className="flex items-center gap-4 mb-4 text-[11px] text-slate-500 flex-wrap">
      {items.map((code) => (
        <span key={code} className="flex items-center gap-1.5">
          <span className="w-3 h-3 rounded-sm inline-block" style={{ background: dept(code).bar }} /> {dept(code).name}
        </span>
      ))}
      <span className="flex items-center gap-1.5">
        <span className="w-6 h-3 rounded-sm inline-block" style={{ background: 'linear-gradient(90deg,#0ea5e9 50%,#8b5cf6 50%)' }} /> Multi-department block
      </span>
    </div>
  )
}

function EmptyState() {
  return (
    <div className="bg-white rounded-xl border border-dashed border-slate-300 p-10 text-center">
      <div className="text-3xl mb-2">🗓️</div>
      <div className="font-semibold text-slate-700">No schedule yet</div>
      <p className="text-sm text-slate-500 mt-1">Click <span className="font-semibold text-rail-accent">Run AI Planner</span> at the top to generate the optimized block plan.</p>
    </div>
  )
}

function Stat({ label, value }) {
  return (
    <div className="bg-slate-50 rounded-lg p-2">
      <div className="text-slate-500">{label}</div>
      <div className="font-bold text-slate-700">{value}</div>
    </div>
  )
}
