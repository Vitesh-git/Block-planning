import axios from 'axios'

// Base URL: in dev, Vite proxies /api -> backend. In production set VITE_API_BASE.
const API_BASE = import.meta.env.VITE_API_BASE || '/api/v1'

const api = axios.create({ baseURL: API_BASE, timeout: 60000 })

export const Pipeline = {
  run: (body = { reset: true }) => api.post('/pipeline/run', body).then((r) => r.data),
  prioritize: () => api.post('/pipeline/prioritize').then((r) => r.data),
  optimize: (body = {}) => api.post('/pipeline/optimize', body).then((r) => r.data),
  injectEmergency: (body = {}) => api.post('/pipeline/inject-emergency', body).then((r) => r.data),
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
  update: (id, body) => api.patch(`/tasks/${id}`, body).then((r) => r.data),
  groups: () => api.get('/groups').then((r) => r.data),
}

export const Blocks = {
  list: () => api.get('/blocks').then((r) => r.data),
  update: (id, body) => api.patch(`/blocks/${id}`, body).then((r) => r.data),
  unscheduled: () => api.get('/blocks/unscheduled').then((r) => r.data),
}

export const Corridors = {
  list: () => api.get('/corridors').then((r) => r.data),
}

export const reportUrl = (kind, period = 'weekly') =>
  `${API_BASE}/reports/${kind}?period=${period}`

export default api
