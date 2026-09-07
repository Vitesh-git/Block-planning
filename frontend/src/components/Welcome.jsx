import { usePipeline } from '../hooks/usePipeline'
import { PipelineProgress } from './PipelineFlow'
import Stepper from './Stepper'

// First-run / empty state. Explains the tool in one line and gives a single
// unmistakable action to generate the plan.
export default function Welcome({ onDone }) {
  const { running, stage, error, run } = usePipeline(onDone)

  return (
    <div className="max-w-3xl mx-auto mt-6">
      <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-8 text-center">
        <div className="text-5xl mb-3">🚆</div>
        <h2 className="text-2xl font-extrabold text-slate-800">Automatic Block Planning</h2>
        <p className="text-slate-500 mt-2 max-w-xl mx-auto">
          Turn track, signalling and OHE maintenance backlogs into an optimized set of
          traffic blocks — high-priority work first, departments combined, line
          possessions kept to a minimum. Start by generating a plan.
        </p>

        {!running ? (
          <button
            onClick={run}
            className="mt-6 inline-flex items-center gap-2 bg-rail-accent hover:bg-blue-700 text-white font-semibold px-6 py-3 rounded-xl shadow-sm text-base"
          >
            ⚙️ Generate Optimized Plan
          </button>
        ) : (
          <div className="mt-6 max-w-sm mx-auto text-left">
            <PipelineProgress stage={stage} />
          </div>
        )}

        {error && (
          <div className="mt-4 text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
            {error}
          </div>
        )}

        <p className="text-[11px] text-slate-400 mt-5">
          Runs the full pipeline: data integration → AI prioritization → OR-Tools optimization. Takes a few seconds.
        </p>
      </div>

      <div className="mt-5">
        <Stepper current={0} />
      </div>
    </div>
  )
}
