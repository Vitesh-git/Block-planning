import { useEffect, useMemo, useState } from 'react'
import { Planning, errorText } from '../api/client'
import { useCorridorNames } from '../hooks/useCorridorNames'

// Live-event control for dynamic rescheduling. An event (emergency defect,
// window withdrawn / shortened by Control, or a manual re-plan) is applied to
// the current plan; approved blocks stay frozen unless the event breaks them,
// and a new plan version records what changed.
const EVENTS = [
  { type: 'EMERGENCY_DEFECT', label: '⚡ Emergency defect' },
  { type: 'WINDOW_CANCELLED', label: '⛔ Window cancelled by Control' },
  { type: 'WINDOW_REDUCED', label: '⏱ Window shortened' },
  { type: 'REPLAN', label: '🔁 Re-plan (keep approved)' },
]

export default function RescheduleControl({ onDone, className = '' }) {
  const [open, setOpen] = useState(false)
  const [type, setType] = useState('EMERGENCY_DEFECT')
  const [windows, setWindows] = useState([])
  const [form, setForm] = useState({ corridor_id: '', window_id: '', new_minutes: 90, duration_min: 60, reason: '' })
  const [running, setRunning] = useState(false)
  const [flash, setFlash] = useState(null)
  const corridorName = useCorridorNames()

  useEffect(() => {
    if (open) Planning.windows().then(setWindows).catch(() => setWindows([]))
  }, [open])

  const granted = useMemo(() => windows.filter((w) => w.status === 'GRANTED'), [windows])
  const corridors = useMemo(() => [...new Set(windows.map((w) => w.corridor_id))], [windows])
  const needsWindow = type === 'WINDOW_CANCELLED' || type === 'WINDOW_REDUCED'
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }))

  const submit = async () => {
    if (needsWindow && !form.window_id) { setFlash({ ok: false, text: 'Choose the affected window.' }); return }
    setRunning(true); setFlash(null)
    try {
      const body = { type, reason: form.reason || undefined }
      if (type === 'EMERGENCY_DEFECT') Object.assign(body, { corridor_id: form.corridor_id || undefined, duration_min: Number(form.duration_min) })
      if (needsWindow) body.window_id = Number(form.window_id)
      if (type === 'WINDOW_REDUCED') body.new_minutes = Number(form.new_minutes)
      const res = await Planning.reschedule(body)
      const o = res.optimization, d = o.diff || {}, ev = res.event || {}
      const head = type === 'EMERGENCY_DEFECT'
        ? `${ev.source_id} (${ev.priority_label}) ${ev.scheduled ? 'scheduled' : 'could not be fitted'}. `
        : ''
      setFlash({
        ok: true,
        text: `${head}Plan v${o.version}: +${d.added ?? 0} added, ${d.moved ?? 0} moved, ${d.dropped ?? 0} dropped · ${o.kept_approved_blocks} approved block(s) kept.`,
      })
      setOpen(false)
      onDone && onDone(res)
    } catch (e) {
      setFlash({ ok: false, text: errorText(e, 'Re-plan failed') })
    } finally {
      setRunning(false)
    }
  }

  return (
    <div className={`relative flex items-center gap-2 ${className}`}>
      {flash && (
        <span className={`text-xs rounded-lg px-2.5 py-1.5 border max-w-md ${flash.ok ? 'text-amber-800 bg-amber-50 border-amber-200' : 'text-red-600 bg-red-50 border-red-200'}`}>
          {flash.text}
          <button onClick={() => setFlash(null)} className="ml-1 opacity-60 hover:opacity-100" aria-label="Dismiss">×</button>
        </span>
      )}
      <button
        onClick={() => setOpen((v) => !v)}
        disabled={running}
        aria-expanded={open}
        className="inline-flex items-center gap-1.5 bg-red-600 hover:bg-red-700 disabled:opacity-60 text-white text-sm font-semibold px-3 py-2 rounded-lg shadow-sm whitespace-nowrap"
      >
        {running ? <span className="w-4 h-4 border-2 border-white/40 border-t-white rounded-full animate-spin" /> : '⚡'}
        {running ? 'Re-planning…' : 'Live event'}
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-2 z-[600] w-80 bg-white rounded-xl border border-slate-200 shadow-xl p-4 space-y-3 text-sm">
          <div className="font-bold text-slate-700">Real-time rescheduling</div>
          <div className="space-y-1">
            {EVENTS.map((e) => (
              <label key={e.type} className="flex items-center gap-2 text-xs text-slate-700 cursor-pointer">
                <input type="radio" name="evt" checked={type === e.type} onChange={() => setType(e.type)} /> {e.label}
              </label>
            ))}
          </div>

          {type === 'EMERGENCY_DEFECT' && (
            <div className="grid grid-cols-2 gap-2">
              <Field label="Corridor">
                <select value={form.corridor_id} onChange={set('corridor_id')} className={INPUT}>
                  <option value="">Busiest (auto)</option>
                  {corridors.map((c) => <option key={c} value={c}>{corridorName(c)}</option>)}
                </select>
              </Field>
              <Field label="Work (min)">
                <input type="number" min={15} max={360} value={form.duration_min} onChange={set('duration_min')} className={INPUT} />
              </Field>
            </div>
          )}

          {needsWindow && (
            <Field label="Affected window">
              <select value={form.window_id} onChange={set('window_id')} className={INPUT}>
                <option value="">Select…</option>
                {granted.map((w) => (
                  <option key={w.id} value={w.id}>{w.date} · {w.start}–{w.end} · {corridorName(w.corridor_id)}</option>
                ))}
              </select>
            </Field>
          )}
          {type === 'WINDOW_REDUCED' && (
            <Field label="New window length (min)">
              <input type="number" min={15} max={600} value={form.new_minutes} onChange={set('new_minutes')} className={INPUT} />
            </Field>
          )}

          <Field label="Reason (recorded in the audit trail)">
            <input value={form.reason} maxLength={500} onChange={set('reason')} placeholder="e.g. Control message 14:05" className={INPUT} />
          </Field>

          <div className="flex gap-2">
            <button onClick={submit} disabled={running} className="flex-1 bg-rail-accent hover:bg-blue-700 disabled:opacity-60 text-white text-xs font-semibold px-3 py-2 rounded-lg">
              Apply &amp; re-plan
            </button>
            <button onClick={() => setOpen(false)} className="text-xs px-3 py-2 rounded-lg bg-slate-100 text-slate-600">Cancel</button>
          </div>
          <p className="text-[10px] text-slate-400 leading-snug">Approved blocks are kept unless this event invalidates them; everything else is re-optimized.</p>
        </div>
      )}
    </div>
  )
}

const INPUT = 'w-full border border-slate-200 rounded-md px-2 py-1.5 text-xs bg-white text-slate-700'

function Field({ label, children }) {
  return (
    <label className="block">
      <span className="block text-[10px] font-semibold text-slate-500 mb-0.5">{label}</span>
      {children}
    </label>
  )
}
