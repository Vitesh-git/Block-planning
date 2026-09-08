import { dept, deptBar } from '../utils/domain'

// Original "time–space" allocation view: maintenance blocks placed on a 24-hour
// axis per corridor, concentrated in the protected low-traffic night window.
// Each block shows a translucent safety buffer around the solid possession bar.
const HOURS = [0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22, 24]
const DAY_MIN = 24 * 60
const NIGHT_START = 0     // 00:00
const NIGHT_END = 6 * 60  // 06:00 — protected maintenance window

const toMin = (hhmm) => {
  const [h, m] = (hhmm || '0:0').split(':').map(Number)
  return h * 60 + m
}

function barBg(departments) {
  const codes = (departments || '').split(',').filter(Boolean)
  if (codes.length <= 1) {
    const c = deptBar(codes[0] || '')
    return `linear-gradient(180deg, ${c}, ${c})`
  }
  const n = codes.length
  const stops = codes
    .map((c, i) => `${deptBar(c)} ${Math.round((i / n) * 100)}% ${Math.round(((i + 1) / n) * 100)}%`)
    .join(', ')
  return `linear-gradient(90deg, ${stops})`
}

export default function GanttSchedule({ blocks, corridorName, selected, onSelect }) {
  if (!blocks || blocks.length === 0) {
    return <div className="text-slate-400 text-sm p-4">No blocks to plot yet.</div>
  }
  const byDate = {}
  blocks.forEach((b) => { (byDate[b.date] = byDate[b.date] || []).push(b) })
  const dates = Object.keys(byDate).sort()
  const nightPct = [(NIGHT_START / DAY_MIN) * 100, (NIGHT_END / DAY_MIN) * 100]

  return (
    <div className="space-y-6">
      {dates.map((d) => (
        <div key={d}>
          <div className="flex items-center gap-2 mb-2">
            <span className="text-sm font-bold text-slate-800">
              {new Date(d).toLocaleDateString('en-IN', { weekday: 'long', day: '2-digit', month: 'short' })}
            </span>
            <span className="text-[11px] text-slate-400">{byDate[d].length} possession{byDate[d].length > 1 ? 's' : ''}</span>
          </div>

          {/* hour axis */}
          <div className="relative ml-44 h-4 mb-1 select-none">
            {HOURS.map((h) => (
              <span key={h} className="absolute -translate-x-1/2 text-[10px] font-medium text-slate-400" style={{ left: `${(h / 24) * 100}%` }}>
                {String(h).padStart(2, '0')}
              </span>
            ))}
          </div>

          <div className="space-y-2">
            {byDate[d]
              .slice()
              .sort((a, b) => a.corridor_id.localeCompare(b.corridor_id) || toMin(a.start_time) - toMin(b.start_time))
              .map((b) => {
                let start = toMin(b.start_time)
                let end = toMin(b.end_time)
                if (end <= start) end += DAY_MIN
                const left = (start / DAY_MIN) * 100
                const width = Math.max(((end - start) / DAY_MIN) * 100, 3.2)
                const isSel = selected?.id === b.id
                const codes = (b.departments || '').split(',').filter(Boolean)
                return (
                  <div key={b.id ?? b.block_ref} className="flex items-center gap-2">
                    <div className="w-44 shrink-0 text-right pr-3 truncate text-[11px] font-medium text-slate-600" title={corridorName(b.corridor_id)}>
                      {corridorName(b.corridor_id)}
                    </div>
                    <div className="relative flex-1 h-9 rounded-lg bg-slate-50 border border-slate-100 overflow-hidden">
                      {/* protected night window shading */}
                      <span className="absolute inset-y-0 bg-indigo-500/[0.06] border-r border-indigo-300/30"
                        style={{ left: `${nightPct[0]}%`, width: `${nightPct[1] - nightPct[0]}%` }} />
                      {/* 2-hour gridlines */}
                      {HOURS.slice(1, -1).map((h) => (
                        <span key={h} className="absolute top-0 bottom-0 w-px bg-slate-200/60" style={{ left: `${(h / 24) * 100}%` }} />
                      ))}
                      {/* safety buffer (translucent halo around the possession) */}
                      <span className="absolute top-1 bottom-1 rounded-md"
                        style={{ left: `calc(${left}% - 5px)`, width: `calc(${width}% + 10px)`, minWidth: 54, background: barBg(b.departments), opacity: 0.18 }} />
                      {/* possession bar */}
                      <button
                        onClick={() => onSelect && onSelect(b)}
                        title={`${corridorName(b.corridor_id)} · ${b.start_time}–${b.end_time} · ${b.task_count} tasks · ${codes.map((c) => dept(c).short).join(' + ')}`}
                        className={`absolute top-1.5 bottom-1.5 rounded-md flex items-center px-2 text-[10px] font-semibold text-white overflow-hidden shadow-sm transition-all duration-150 hover:brightness-110 hover:-translate-y-px ${isSel ? 'ring-2 ring-slate-800 ring-offset-1' : ''}`}
                        style={{ left: `${left}%`, width: `${width}%`, minWidth: 48, background: barBg(b.departments) }}
                      >
                        <span className="truncate drop-shadow-sm">{b.start_time}–{b.end_time} · {b.task_count}</span>
                      </button>
                    </div>
                  </div>
                )
              })}
          </div>
        </div>
      ))}
    </div>
  )
}
