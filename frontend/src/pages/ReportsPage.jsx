import { useEffect, useState, useCallback } from 'react'
import { Pipeline, reportUrl } from '../api/client'
import Header from '../components/Header.jsx'

// Downloadable PDF / Excel reports + AI engine transparency.
export default function ReportsPage() {
  const [period, setPeriod] = useState('weekly')
  const [model, setModel] = useState(null)

  const load = useCallback(async () => {
    try { setModel(await Pipeline.modelInfo()) } catch { /* not trained yet */ }
  }, [])
  useEffect(() => { load() }, [load])

  const topFeatures = model?.feature_importances
    ? Object.entries(model.feature_importances).sort((a, b) => b[1] - a[1]).slice(0, 6)
    : []
  const stages = model?.engine?.stages || []

  return (
    <>
      <Header title="Reports & AI Engine" subtitle="Downloadable block plans and model transparency" onRefresh={load} />
      <div className="p-6 space-y-6">
        {/* Two-stage engine explanation */}
        {stages.length > 0 && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {stages.map((s, i) => (
              <div key={s.name} className={`rounded-xl border shadow-sm p-4 ${i === 1 ? 'border-rail-accent/40 bg-blue-50/40' : 'border-slate-200 bg-white'}`}>
                <div className="flex items-center gap-2">
                  <span className="w-7 h-7 rounded-lg bg-rail-accent text-white flex items-center justify-center text-xs font-bold">{i + 1}</span>
                  <div>
                    <div className="font-bold text-slate-800 text-sm">{s.name}</div>
                    <div className="text-[11px] text-slate-500">{s.kind}</div>
                  </div>
                </div>
                <p className="text-xs text-slate-600 mt-2 leading-snug">{s.role}</p>
              </div>
            ))}
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-5">
            <h3 className="font-bold text-slate-700 mb-3">Download Block Plan</h3>
            <div className="flex gap-2 mb-4">
              {['weekly', 'monthly'].map((p) => (
                <button key={p} onClick={() => setPeriod(p)}
                  className={`px-3 py-1.5 rounded-lg text-sm font-semibold capitalize ${period === p ? 'bg-rail-accent text-white' : 'bg-slate-100 text-slate-600'}`}>
                  {p}
                </button>
              ))}
            </div>
            <div className="flex gap-3">
              <a href={reportUrl('pdf', period)} target="_blank" rel="noreferrer"
                className="flex-1 flex items-center gap-2 justify-center bg-red-600 hover:bg-red-700 text-white font-semibold px-4 py-3 rounded-lg">
                📄 Download PDF
              </a>
              <a href={reportUrl('excel', period)} target="_blank" rel="noreferrer"
                className="flex-1 flex items-center gap-2 justify-center bg-emerald-600 hover:bg-emerald-700 text-white font-semibold px-4 py-3 rounded-lg">
                📊 Download Excel
              </a>
            </div>
            <p className="text-[11px] text-slate-500 mt-3">
              Reports include the full {period} block schedule, department combination, utilization and detailed task allocation.
            </p>
          </div>

          <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-5">
            <h3 className="font-bold text-slate-700 mb-3">Priority Engine — model details</h3>
            {model ? (
              <>
                <div className="grid grid-cols-3 gap-2 text-center text-sm mb-4">
                  <Stat label="Algorithm" value={model.algorithm} />
                  <Stat label="Accuracy" value={`${Math.round(model.accuracy * 100)}%`} />
                  <Stat label="Classes" value={model.classes?.length} />
                </div>
                <div className="text-xs font-semibold text-slate-600 mb-2">Top priority drivers (feature importance)</div>
                <div className="space-y-1.5">
                  {topFeatures.map(([f, v]) => (
                    <div key={f}>
                      <div className="flex justify-between text-[11px] text-slate-500">
                        <span>{f}</span><span>{(v * 100).toFixed(0)}%</span>
                      </div>
                      <div className="h-2 bg-slate-100 rounded">
                        <div className="h-2 bg-rail-accent rounded" style={{ width: `${Math.min(100, v * 100 / (topFeatures[0][1] || 1))}%` }} />
                      </div>
                    </div>
                  ))}
                </div>
              </>
            ) : (
              <div className="text-slate-400 text-sm">Run the AI Planner to train and load the model.</div>
            )}
          </div>
        </div>
      </div>
    </>
  )
}

function Stat({ label, value }) {
  return (
    <div className="bg-slate-50 rounded-lg p-2">
      <div className="text-[10px] text-slate-500 uppercase">{label}</div>
      <div className="font-bold text-slate-700 text-sm">{value}</div>
    </div>
  )
}
