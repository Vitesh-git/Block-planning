// Central domain vocabulary for the Automatic Block Planning System.
// Internal codes (ENG/SNT/TRD) are preserved everywhere; this module maps them
// to realistic Indian Railways department names, colours and source systems,
// and defines a glossary of railway terms surfaced as tooltips in the UI.

export const DEPARTMENTS = {
  ENG: {
    code: 'ENG',
    short: 'ENGG',
    name: 'Engineering (P.Way)',
    full: 'Engineering Department — Permanent Way (track)',
    system: 'TMS · Track Management System',
    badge: 'bg-sky-100 text-sky-700 ring-sky-600/20',
    bar: '#0ea5e9',
  },
  SNT: {
    code: 'SNT',
    short: 'S&T',
    name: 'Signal & Telecom',
    full: 'Signal & Telecommunication Department',
    system: 'SMMS · Signal Maintenance Management System',
    badge: 'bg-violet-100 text-violet-700 ring-violet-600/20',
    bar: '#8b5cf6',
  },
  TRD: {
    code: 'TRD',
    short: 'TRD',
    name: 'Traction Distribution',
    full: 'Traction Distribution — 25 kV Overhead Equipment (OHE)',
    system: 'TDMS · Traction Distribution Management System',
    badge: 'bg-amber-100 text-amber-700 ring-amber-600/20',
    bar: '#f59e0b',
  },
}

// The Operating department (Control Office) grants the possessions the three
// executing departments above work within.
export const CONTROL_OFFICE = {
  name: 'Operating · Control Office (COA)',
  full: 'Operating Department — Control Office Application, the authority that grants traffic blocks',
}

export const DEPT_ORDER = ['ENG', 'SNT', 'TRD']

export function dept(code) {
  return DEPARTMENTS[code] || { code, short: code, name: code, full: code, system: '', badge: 'bg-slate-100 text-slate-600 ring-slate-500/20', bar: '#94a3b8' }
}
export const deptShort = (code) => dept(code).short
export const deptName = (code) => dept(code).name
export const deptFull = (code) => dept(code).full
export const deptBar = (code) => dept(code).bar

// Shorten a corridor id for compact display when the full name isn't loaded yet.
export function corridorShort(id) {
  return (id || '').replace('COR-', '').replace(/-/g, ' – ')
}

// Plain-language glossary for the ⓘ tooltips.
export const GLOSSARY = {
  GMT: 'Gross Million Tonnes — the annual traffic load a corridor carries. Higher GMT means a busier line where possessions are costlier to grant.',
  'Traffic block': 'A planned line possession — a period when trains are held so maintenance gangs can safely work on the track, signalling or OHE.',
  Possession: 'The railway term for a granted traffic block: exclusive access to a section of line for maintenance.',
  Corridor: 'A defined route between two major stations, maintained as one planning unit.',
  Utilization: 'How much of a granted window the planned work actually fills (planned minutes ÷ window minutes).',
  Disruption: 'A 0–1 measure of how costly a possession is to traffic — night blocks on quiet lines are cheap, day blocks on busy corridors are expensive.',
  Coverage: 'Share of block-requiring pending tasks that the optimizer managed to schedule.',
  'Multi-department block': 'A single possession that combines Engineering, S&T and/or Traction work — one line closure instead of several.',
  'Blocks saved': 'Line possessions avoided versus naive planning (one block per corridor, per date, per department).',
}
