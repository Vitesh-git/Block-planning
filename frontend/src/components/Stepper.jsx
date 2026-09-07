// Horizontal workflow stepper that makes the end-to-end flow visible:
// Load data → Prioritize → Optimize → Review → Export.
const STEPS = [
  { label: 'Load data', hint: 'Integrate feeds' },
  { label: 'Prioritize', hint: 'AI scoring' },
  { label: 'Optimize', hint: 'Plan blocks' },
  { label: 'Review', hint: 'Schedule & tasks' },
  { label: 'Export', hint: 'PDF / Excel' },
]

export default function Stepper({ current = 0 }) {
  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-sm px-4 py-3 overflow-x-auto">
      <div className="flex items-center min-w-[640px]">
        {STEPS.map((s, i) => {
          const done = i < current
          const active = i === current
          return (
            <div key={s.label} className="flex items-center flex-1 last:flex-none">
              <div className="flex items-center gap-2">
                <div
                  className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold shrink-0 ${
                    done ? 'bg-emerald-500 text-white'
                      : active ? 'bg-rail-accent text-white ring-4 ring-blue-100'
                      : 'bg-slate-100 text-slate-400'
                  }`}
                >
                  {done ? '✓' : i + 1}
                </div>
                <div className="leading-tight">
                  <div className={`text-xs font-semibold ${active ? 'text-slate-800' : done ? 'text-slate-600' : 'text-slate-400'}`}>{s.label}</div>
                  <div className="text-[10px] text-slate-400 hidden sm:block">{s.hint}</div>
                </div>
              </div>
              {i < STEPS.length - 1 && (
                <div className={`h-0.5 flex-1 mx-3 rounded ${done ? 'bg-emerald-400' : 'bg-slate-200'}`} />
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
