import React from 'react'
import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom'
import Dashboard from './pages/Dashboard'
import Overview from './pages/Overview'
import Report from './pages/Report'
import IdeaRefine from './pages/IdeaRefine'

const navStyle = {
  display: 'flex',
  gap: '1rem',
  padding: '1rem 2rem',
  background: '#1e293b',
  borderBottom: '1px solid #334155',
}

const linkStyle = {
  color: '#94a3b8',
  textDecoration: 'none',
  padding: '0.5rem 1rem',
  borderRadius: '0.375rem',
  fontSize: '0.875rem',
  fontWeight: 500,
}

const activeLinkStyle = {
  ...linkStyle,
  color: '#f1f5f9',
  background: '#334155',
}

export default function App() {
  return (
    <BrowserRouter>
      <nav style={navStyle}>
        <span style={{ fontWeight: 700, fontSize: '1.1rem', color: '#f1f5f9', marginRight: '1rem' }}>
          Paper Radar
        </span>
        <NavLink to="/" style={({ isActive }) => isActive ? activeLinkStyle : linkStyle}>Dashboard</NavLink>
        <NavLink to="/overview" style={({ isActive }) => isActive ? activeLinkStyle : linkStyle}>Overview</NavLink>
        <NavLink to="/report" style={({ isActive }) => isActive ? activeLinkStyle : linkStyle}>Report</NavLink>
        <NavLink to="/refine" style={({ isActive }) => isActive ? activeLinkStyle : linkStyle}>Idea Refine</NavLink>
      </nav>

      <main style={{ padding: '2rem', maxWidth: '1400px', margin: '0 auto' }}>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/overview" element={<Overview />} />
          <Route path="/report" element={<Report />} />
          <Route path="/refine" element={<IdeaRefine />} />
          <Route path="/refine/:ideaId" element={<IdeaRefine />} />
        </Routes>
      </main>
    </BrowserRouter>
  )
}
