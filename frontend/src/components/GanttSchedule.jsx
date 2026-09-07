import { dept, deptBar } from '../utils/domain'

// Timeline / Gantt view of the optimized plan: blocks grouped by date, one lane
// per block, positioned on a 24-hour axis. Colour = department; multi-department
// blocks show a blended bar (one possession, several departments).
const HOURS = [0, 3, 6, 9, 12, 15, 18, 21, 24]
const DAY_MIN = 24 * 60

function toMin(hhmm) {
  const [h, m] = (hhmm || '0:0').split(':').map(Number)
  return h * 60 + m
}

function barBackground(departments) {
  const codes = (departments || '').split(',').filter(Boolean)
  if (codes.length <= 1) return deptBar(codes[0] || '')
  // blended bar across the combined departments
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

  return (
    <div className="space-y-5">
      {dates.map((d) => (
        <div key={d}>
          <div className="flex items-center gap-2 mb-1.5">
            <span className="text-sm font-bold text-slate-700">
              {new Date(d).toLocaleDateString('en-IN', { weekday: 'long', day: '2-digit', month: 'short' })}
            </span>
            <span className="text-[11px] text-slate-400">{byDate[d].length} block{byDate[d].length > 1 ? 's' : ''}</span>
          </div>

          {/* hour axis */}
          <div className="relative ml-40 h-4 mb-1">
            {HOURS.map((h) => (
              <span key={h} className="absolute -translate-x-1/2 text-[10px] text-slate-400" style={{ left: `${(h / 24) * 100}%` }}>
                {String(h).padStart(2, '0')}:00
              </span>
            ))}
          </div>

          <div className="space-y-1.5">
            {byDate[d]
              .slice()
              .sort((a, b) => a.corridor_id.localeCompare(b.corridor_id) || toMin(a.start_time) - toMin(b.start_time))
              .map((b) => {
                let start = toMin(b.start_time)
                let end = toMin(b.end_time)
                if (end <= start) end += DAY_MIN
                const left = (start / DAY_MIN) * 100
                const width = Math.max(((end - start) / DAY_MIN) * 100, 3)
                const isSel = selected?.id === b.id
                return (
                  <div key={b.id ?? b.block_ref} className="flex items-center gap-2">
                    <div className="w-40 shrink-0 text-right pr-2 truncate text-[11px] text-slate-600" title={corridorName(b.corridor_id)}>
                      {corridorName(b.corridor_id)}
                    </div>
                    <div className="relative flex-1 h-7 bg-slate-50 rounded border border-slate-100">
                      {/* faint 3-hour gridlines */}
                      {HOURS.slice(1, -1).map((h) => (
                        <span key={h} className="absolute top-0 bottom-0 w-px bg-slate-100" style={{ left: `${(h / 24) * 100}%` }} />
                      ))}
                      <button
                        onClick={() => onSelect && onSelect(b)}
                        title={`${corridorName(b.corridor_id)} · ${b.start_time}–${b.end_time} · ${b.task_count} tasks · ${(b.departments || '').split(',').map((c) => dept(c).short).join(' + ')}`}
                        className={`absolute top-0.5 bottom-0.5 rounded flex items-center px-1.5 text-[10px] font-semibold text-white overflow-hidden shadow-sm transition ${isSel ? 'ring-2 ring-slate-800' : 'hover:brightness-110'}`}
                        style={{ left: `${left}%`, width: `${width}%`, minWidth: 44, background: barBackground(b.departments) }}
                      >
                        <span className="truncate drop-shadow">
                          {b.start_time}–{b.end_time} · {b.task_count}
                        </span>
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
