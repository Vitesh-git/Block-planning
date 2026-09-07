import InfoTip from './InfoTip.jsx'

export default function KpiCard({ label, value, sub, accent = 'blue', icon, info }) {
  const accents = {
    blue: 'from-blue-500 to-blue-700',
    red: 'from-red-500 to-red-700',
    green: 'from-emerald-500 to-emerald-700',
    amber: 'from-amber-500 to-amber-600',
    violet: 'from-violet-500 to-violet-700',
  }
  return (
    <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-4 flex items-center gap-4">
      <div className={`w-12 h-12 rounded-lg bg-gradient-to-br ${accents[accent]} text-white flex items-center justify-center text-xl shadow shrink-0`}>
        {icon}
      </div>
      <div className="min-w-0">
        <div className="text-2xl font-extrabold text-slate-800 leading-none">{value}</div>
        <div className="text-xs font-medium text-slate-600 mt-1 flex items-center">
          {label}
          {info && <InfoTip text={info} label={label} />}
        </div>
        {sub && <div className="text-[11px] text-slate-500 mt-0.5">{sub}</div>}
      </div>
    </div>
  )
}
