const STYLES = {
  APPROVED: 'bg-emerald-100 text-emerald-700 ring-emerald-600/20',
  REJECTED: 'bg-red-100 text-red-700 ring-red-600/20',
  PENDING: 'bg-slate-100 text-slate-500 ring-slate-500/20',
}
const LABEL = { APPROVED: '✓ Approved', REJECTED: '✕ Rejected', PENDING: 'Pending' }

export default function ApprovalBadge({ status = 'PENDING' }) {
  const s = (status || 'PENDING').toUpperCase()
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold ring-1 ring-inset ${STYLES[s] || STYLES.PENDING}`}>
      {LABEL[s] || s}
    </span>
  )
}
