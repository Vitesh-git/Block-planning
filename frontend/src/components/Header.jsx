import { usePipeline, PIPELINE_STAGES } from '../hooks/usePipeline'

export default function Header({ title, subtitle, onRefresh }) {
  const { running, stage, result, error, run, dismiss } = usePipeline(onRefresh)
  const o = result?.optimization || {}

  return (
    <div className="bg-white border-b border-slate-200 px-6 py-4 sticky top-0 z-[500]">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-xl font-extrabold text-slate-800">{title}</h1>
          {subtitle && <p className="text-sm text-slate-500">{subtitle}</p>}
        </div>

        <div className="flex items-center gap-3">
          {/* live status */}
          {running && (
            <span className="flex items-center gap-2 text-xs text-slate-600 max-w-xs">
              <span className="w-3.5 h-3.5 border-2 border-slate-300 border-t-rail-accent rounded-full animate-spin" />
              <span>
                Step {Math.min(stage + 1, 3)}/3 · {PIPELINE_STAGES[Math.min(stage, 2)]?.label}…
              </span>
            </span>
          )}
          {!running && result && (
            <span className="flex items-center gap-2 text-xs text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-lg px-2.5 py-1.5">
              ✓ {o.tasks_scheduled} tasks → {o.blocks_opened} blocks
              {o.multi_dept_blocks ? ` (${o.multi_dept_blocks} multi-dept)` : ''}
              {o.wall_time_s != null ? ` · ${o.wall_time_s}s` : ''}
              <button onClick={dismiss} className="text-emerald-600/60 hover:text-emerald-800 ml-1 leading-none">×</button>
            </span>
          )}
          {!running && error && (
            <span className="text-xs text-red-600 bg-red-50 border border-red-200 rounded-lg px-2.5 py-1.5 max-w-xs">
              {error}
              <button onClick={dismiss} className="text-red-500/60 hover:text-red-700 ml-1">×</button>
            </span>
          )}

          <button
            onClick={run}
            disabled={running}
            className="bg-rail-accent hover:bg-blue-700 disabled:opacity-60 text-white text-sm font-semibold px-4 py-2 rounded-lg shadow-sm flex items-center gap-2 whitespace-nowrap"
          >
            {running ? (
              <span className="w-4 h-4 border-2 border-white/40 border-t-white rounded-full animate-spin" />
            ) : (
              '⚙️'
            )}
            {running ? 'Optimizing…' : 'Run AI Planner'}
          </button>
        </div>
      </div>
    </div>
  )
}
