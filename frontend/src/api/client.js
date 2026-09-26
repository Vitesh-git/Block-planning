import axios from 'axios'

// Base URL: in dev, Vite proxies /api -> backend. In production set VITE_API_BASE.
const API_BASE = import.meta.env.VITE_API_BASE || '/api/v1'

const api = axios.create({ baseURL: API_BASE, timeout: 180000 })

// Who is acting (there is no login in this app): remembered per browser and
// sent with every decision so approvals, overrides and events are attributed.
const ACTOR_KEY = 'abps.actor'
export const getActor = () => { try { return localStorage.getItem(ACTOR_KEY) || '' } catch { return '' } }
export const setActor = (v) => { try { localStorage.setItem(ACTOR_KEY, v) } catch { /* private mode */ } }
const withActor = (body = {}) => ({ actor: getActor() || undefined, ...body })

// Readable error text from an axios error (FastAPI detail string or list).
export const errorText = (e, fallback = 'Request failed') => {
  const d = e?.response?.data?.detail
  if (Array.isArray(d)) return d.map((x) => x.msg).join('; ')
  return d || e?.message || fallback
}

export const Pipeline = {
  run: (body = { reset: true }) => api.post('/pipeline/run', withActor(body)).then((r) => r.data),
  prioritize: () => api.post('/pipeline/prioritize').then((r) => r.data),
  optimize: (body = {}) => api.post('/pipeline/optimize', body).then((r) => r.data),
  injectEmergency: (body = {}) => api.post('/pipeline/inject-emergency', withActor(body)).then((r) => r.data),
  modelInfo: () => api.get('/pipeline/model-info').then((r) => r.data),
}

export const Dashboard = {
  kpis: () => api.get('/dashboard/kpis').then((r) => r.data),
  priorityDistribution: () => api.get('/dashboard/priority-distribution').then((r) => r.data),
  departmentLoad: () => api.get('/dashboard/department-load').then((r) => r.data),
  blockUtilization: () => api.get('/dashboard/block-utilization').then((r) => r.data),
  calendar: () => api.get('/dashboard/calendar').then((r) => r.data),
  map: () => api.get('/dashboard/map').then((r) => r.data),
  completion: () => api.get('/dashboard/completion').then((r) => r.data),
}

export const Tasks = {
  list: (params = {}) => api.get('/tasks', { params }).then((r) => r.data),
  update: (id, body) => api.patch(`/tasks/${id}`, withActor(body)).then((r) => r.data),
  groups: () => api.get('/groups').then((r) => r.data),
}

export const Blocks = {
  list: () => api.get('/blocks').then((r) => r.data),
  update: (id, body) => api.patch(`/blocks/${id}`, withActor(body)).then((r) => r.data),
  approveAll: (note) => api.post('/blocks/approve-all', withActor({ note })).then((r) => r.data),
  unscheduled: () => api.get('/blocks/unscheduled').then((r) => r.data),
}

export const Planning = {
  forecast: (params = {}) => api.get('/forecast/traffic', { params }).then((r) => r.data),
  windows: (params = {}) => api.get('/windows', { params }).then((r) => r.data),
  simulate: (body) => api.post('/simulate', withActor(body)).then((r) => r.data),
  scenarios: () => api.get('/scenarios').then((r) => r.data),
  deleteScenario: (id) => api.delete(`/scenarios/${id}`).then((r) => r.data),
  reschedule: (body) => api.post('/reschedule', withActor(body)).then((r) => r.data),
  versions: (limit = 20) => api.get('/plan/versions', { params: { limit } }).then((r) => r.data),
  audit: (params = {}) => api.get('/audit', { params }).then((r) => r.data),
}

export const Corridors = {
  list: () => api.get('/corridors').then((r) => r.data),
}

export const reportUrl = (kind, period = 'weekly') =>
  `${API_BASE}/reports/${kind}?period=${period}`

export default api
