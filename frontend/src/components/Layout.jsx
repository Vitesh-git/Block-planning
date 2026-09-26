import { useState } from 'react'
import { NavLink } from 'react-router-dom'
import { getActor, setActor } from '../api/client'

const NAV = [
  { to: '/', label: 'Dashboard', icon: '📊' },
  { to: '/schedule', label: 'AI Schedule', icon: '🗓️' },
  { to: '/tasks', label: 'Prioritized Tasks', icon: '🚦' },
  { to: '/map', label: 'Corridor Map', icon: '🗺️' },
  { to: '/lab', label: 'Planning Lab', icon: '🧪' },
  { to: '/reports', label: 'Reports', icon: '📄' },
]

export default function Layout({ children }) {
  return (
    <div className="min-h-screen flex bg-slate-100">
      <aside className="w-64 shrink-0 bg-rail-navy text-slate-100 flex flex-col">
        <div className="px-5 py-5 border-b border-white/10">
          <div className="flex items-center gap-2">
            <span className="text-2xl">🚆</span>
            <div>
              <div className="font-extrabold leading-tight">Block Planner</div>
              <div className="text-[11px] text-slate-400">Indian Railways · ABPS</div>
            </div>
          </div>
        </div>
        <nav className="flex-1 py-4 space-y-1 px-3">
          {NAV.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              end={n.to === '/'}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition ${
                  isActive
                    ? 'bg-rail-accent text-white shadow'
                    : 'text-slate-300 hover:bg-white/10'
                }`
              }
            >
              <span>{n.icon}</span>
              {n.label}
            </NavLink>
          ))}
        </nav>
        <ActorField />
        <div className="px-5 py-4 text-[11px] text-slate-400 border-t border-white/10">
          Automatic Block Planning System<br />
          Engineering · S&amp;T · Traction
        </div>
      </aside>
      <main className="flex-1 overflow-x-hidden">{children}</main>
    </div>
  )
}

// Name recorded on approvals, overrides and live events (no login in this app).
function ActorField() {
  const [name, setName] = useState(getActor())
  return (
    <label className="block px-5 py-3 border-t border-white/10">
      <span className="text-[10px] uppercase tracking-wide text-slate-400">Acting as</span>
      <input
        value={name}
        maxLength={64}
        placeholder="Your name / designation"
        onChange={(e) => { setName(e.target.value); setActor(e.target.value.trim()) }}
        className="mt-1 w-full rounded-md bg-white/10 border border-white/10 px-2 py-1.5 text-xs text-white placeholder:text-slate-500 focus:outline-none focus:ring-1 focus:ring-rail-accent"
      />
    </label>
  )
}
