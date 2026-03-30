import { HashRouter, Routes, Route } from 'react-router-dom'
import { ChatPage } from './pages/ChatPage'
import { DashboardPage } from './pages/DashboardPage'
import { SupervisorPage } from './pages/SupervisorPage'
import { ProfilePage } from './pages/ProfilePage'
import { PrivacyPolicyPage } from './pages/PrivacyPolicyPage'

export function App() {
  return (
    <HashRouter>
      <Routes>
        <Route path="/" element={<ChatPage />} />
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/supervisor" element={<SupervisorPage />} />
        <Route path="/profile" element={<ProfilePage />} />
        <Route path="/privacy-policy" element={<PrivacyPolicyPage />} />
      </Routes>
    </HashRouter>
  )
}
