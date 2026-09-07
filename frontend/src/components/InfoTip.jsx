import { useState } from 'react'

// Lightweight, dependency-free tooltip. Renders a small ⓘ (or wraps children)
// and shows explanatory text on hover/focus. Used to demystify railway jargon.
export default function InfoTip({ text, label, children, className = '' }) {
  const [open, setOpen] = useState(false)
  return (
    <span
      className={`relative inline-flex items-center ${className}`}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onFocus={() => setOpen(true)}
      onBlur={() => setOpen(false)}
      tabIndex={0}
    >
      {children ? (
        <span className="border-b border-dotted border-slate-400 cursor-help">{children}</span>
      ) : (
        <span className="ml-1 w-4 h-4 rounded-full bg-slate-200 text-slate-600 text-[10px] font-bold flex items-center justify-center cursor-help select-none">i</span>
      )}
      {open && (
        <span className="absolute z-[1000] left-1/2 -translate-x-1/2 bottom-full mb-2 w-64 rounded-lg bg-slate-800 text-slate-100 text-[11px] leading-snug font-normal px-3 py-2 shadow-lg pointer-events-none">
          {label && <span className="block font-semibold text-white mb-0.5">{label}</span>}
          {text}
          <span className="absolute left-1/2 -translate-x-1/2 top-full border-4 border-transparent border-t-slate-800" />
        </span>
      )}
    </span>
  )
}
