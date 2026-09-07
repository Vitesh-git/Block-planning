import { dept as deptInfo } from '../utils/domain'

const STYLES = {
  Critical: 'bg-red-100 text-red-700 ring-red-600/20',
  High: 'bg-orange-100 text-orange-700 ring-orange-600/20',
  Medium: 'bg-yellow-100 text-yellow-800 ring-yellow-600/20',
  Low: 'bg-green-100 text-green-700 ring-green-600/20',
}

export default function PriorityBadge({ label }) {
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold ring-1 ring-inset ${
        STYLES[label] || 'bg-slate-100 text-slate-600 ring-slate-500/20'
      }`}
    >
      {label || '—'}
    </span>
  )
}

// Department chip showing the realistic short code; the native title tooltip
// reveals the full Indian Railways department name on hover.
export function DeptBadge({ dept, showName = false }) {
  const d = deptInfo(dept)
  return (
    <span
      title={d.full}
      className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-semibold ring-1 ring-inset cursor-help ${d.badge}`}
    >
      {showName ? d.name : d.short}
    </span>
  )
}

export const DEPT_STYLE = {
  ENG: deptInfo('ENG').badge,
  SNT: deptInfo('SNT').badge,
  TRD: deptInfo('TRD').badge,
}
