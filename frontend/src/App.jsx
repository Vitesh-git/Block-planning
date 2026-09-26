import { Routes, Route } from 'react-router-dom'
import Layout from './components/Layout.jsx'
import DashboardPage from './pages/DashboardPage.jsx'
import SchedulePage from './pages/SchedulePage.jsx'
import TasksPage from './pages/TasksPage.jsx'
import MapPage from './pages/MapPage.jsx'
import ReportsPage from './pages/ReportsPage.jsx'
import PlanningLabPage from './pages/PlanningLabPage.jsx'

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<DashboardPage />} />
        <Route path="/schedule" element={<SchedulePage />} />
        <Route path="/tasks" element={<TasksPage />} />
        <Route path="/map" element={<MapPage />} />
        <Route path="/lab" element={<PlanningLabPage />} />
        <Route path="/reports" element={<ReportsPage />} />
      </Routes>
    </Layout>
  )
}
