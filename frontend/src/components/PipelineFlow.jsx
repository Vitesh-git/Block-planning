import { PIPELINE_STAGES } from '../hooks/usePipeline'

// Staged progress list shown while the pipeline runs.
export function PipelineProgress({ stage }) {
  return (
    <div className="space-y-2">
      {PIPELINE_STAGES.map((s, i) => {
        const done = stage > i
        const active = stage === i
        return (
          <div key={s.key} className="flex items-center gap-3">
            <span
              className={`w-5 h-5 rounded-full flex items-center justify-center text-[11px] shrink-0 ${
                done ? 'bg-emerald-500 text-white'
                  : active ? 'bg-rail-accent text-white'
                  : 'bg-slate-200 text-slate-400'
              }`}
            >
              {done ? '✓' : active ? '' : i + 1}
              {active && <span className="w-3 h-3 border-2 border-white/50 border-t-white rounded-full animate-spin" />}
            </span>
            <div className="leading-tight">
              <div className={`text-sm font-medium ${done || active ? 'text-slate-700' : 'text-slate-400'}`}>{s.label}</div>
              <div className="text-[11px] text-slate-400">{s.detail}</div>
            </div>
          </div>
        )
      })}
    </div>
  )
}

// Result summary card shown after a successful run.
export function PipelineResult({ result, onDismiss }) {
  if (!result) return null
  const o = result.optimization || {}
  const integ = result.data_integration || {}
  const saved = typeof o.blocks_saved_vs_naive === 'number' ? o.blocks_saved_vs_naive : null
  return (
    <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="font-bold text-emerald-800 text-sm">✓ Optimized plan ready</div>
        {onDismiss && (
          <button onClick={onDismiss} className="text-emerald-700/60 hover:text-emerald-800 text-lg leading-none">×</button>
        )}
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mt-3">
        <Metric v={o.tasks_scheduled} l="tasks scheduled" />
        <Metric v={o.blocks_opened} l="blocks planned" />
        <Metric v={o.multi_dept_blocks} l="multi-dept blocks" />
        <Metric v={`${o.wall_time_s ?? '—'}s`} l="solve time" />
      </div>
      <p className="text-xs text-emerald-800/80 mt-3">
        {integ.total_tasks ? `${integ.total_tasks} maintenance tasks` : 'Tasks'} across {' '}
        {Object.keys(integ.by_department || {}).length || 3} departments were prioritized and coordinated into {o.blocks_opened} shared possessions
        {o.multi_dept_blocks ? `, ${o.multi_dept_blocks} of them combining multiple departments into one line closure` : ''}.
      </p>
    </div>
  )
}

function Metric({ v, l }) {
  return (
    <div className="bg-white/70 rounded-lg px-2 py-1.5 text-center">
      <div className="text-lg font-extrabold text-emerald-800 leading-none">{v ?? '—'}</div>
      <div className="text-[10px] text-emerald-700/70 mt-0.5">{l}</div>
    </div>
  )
}
