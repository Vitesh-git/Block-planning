import { useState } from 'react'
import { Pipeline } from '../api/client'

// What-if control: injects an urgent critical defect, re-runs the planner, and
// reports whether the plan absorbed it — a live-demo moment.
export default function InjectEmergencyButton({ onDone, className = '' }) {
  const [running, setRunning] = useState(false)
  const [flash, setFlash] = useState(null)

  const go = async () => {
    setRunning(true); setFlash(null)
    try {
      const res = await Pipeline.injectEmergency({})
      setFlash({
        ok: true,
        text: `Emergency ${res.injected.source_id} (${res.injected.priority_label}) ${res.scheduled ? 'was scheduled into the plan' : 'could not be fit into a window'} — replanned into ${res.optimization.blocks_opened} blocks.`,
      })
      onDone && onDone(res)
    } catch (e) {
      setFlash({ ok: false, text: e?.response?.data?.detail || e?.message || 'Injection failed' })
    } finally {
      setRunning(false)
    }
  }

  return (
    <div className={`flex items-center gap-2 ${className}`}>
      <button
        onClick={go}
        disabled={running}
        title="Inject an emergency critical defect and re-run the optimizer"
        className="inline-flex items-center gap-1.5 bg-red-600 hover:bg-red-700 disabled:opacity-60 text-white text-sm font-semibold px-3 py-2 rounded-lg shadow-sm whitespace-nowrap"
      >
        {running ? <span className="w-4 h-4 border-2 border-white/40 border-t-white rounded-full animate-spin" /> : '⚡'}
        {running ? 'Replanning…' : 'Inject Emergency'}
      </button>
      {flash && (
        <span className={`text-xs rounded-lg px-2.5 py-1.5 border max-w-sm ${flash.ok ? 'text-amber-800 bg-amber-50 border-amber-200' : 'text-red-600 bg-red-50 border-red-200'}`}>
          {flash.text}
        </span>
      )}
    </div>
  )
}
