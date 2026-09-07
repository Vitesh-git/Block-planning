import { useRef, useState } from 'react'
import { Pipeline } from '../api/client'

// The three real pipeline stages. The backend runs them in a single request;
// we advance the on-screen stage on a timer so the user can watch the actual
// stages progress, then show the true result when the request returns.
export const PIPELINE_STAGES = [
  { key: 'integrate', label: 'Integrating departmental feeds', detail: 'TMS · SMMS · TDMS · Control Office' },
  { key: 'prioritize', label: 'Scoring & explaining priorities', detail: 'Explainable Priority Engine' },
  { key: 'optimize', label: 'Optimizing traffic blocks', detail: 'OR-Tools CP-SAT constraint solver' },
]

export function usePipeline(onDone) {
  const [running, setRunning] = useState(false)
  const [stage, setStage] = useState(-1) // -1 idle, 0..2 running a stage, 3 done
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')
  const timers = useRef([])

  const clearTimers = () => { timers.current.forEach(clearTimeout); timers.current = [] }

  const run = async () => {
    setRunning(true); setResult(null); setError(''); setStage(0)
    clearTimers()
    timers.current.push(setTimeout(() => setStage((s) => (s < 1 ? 1 : s)), 1000))
    timers.current.push(setTimeout(() => setStage((s) => (s < 2 ? 2 : s)), 2200))
    try {
      const res = await Pipeline.run({ reset: true })
      clearTimers()
      setStage(3)
      setResult(res)
      onDone && onDone(res)
    } catch (e) {
      clearTimers()
      setStage(-1)
      setError(e?.response?.data?.detail || e?.message || 'Pipeline failed')
    } finally {
      setRunning(false)
    }
  }

  const dismiss = () => { setResult(null); setError(''); setStage(-1) }

  return { running, stage, result, error, run, dismiss }
}
