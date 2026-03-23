import { HashRouter, Routes, Route } from 'react-router-dom'
import { ChatPage } from './pages/ChatPage'
import { DashboardPage } from './pages/DashboardPage'
import { SupervisorPage } from './pages/SupervisorPage'

export function App() {
  return (
    <HashRouter>
      <Routes>
        <Route path="/" element={<ChatPage />} />
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/supervisor" element={<SupervisorPage />} />
      </Routes>
    </HashRouter>
  )
}
