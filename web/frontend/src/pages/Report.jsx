import React, { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'

const cardStyle = {
  background: '#1e293b',
  borderRadius: '0.75rem',
  padding: '1.5rem',
  border: '1px solid #334155',
}

const statCardStyle = {
  ...cardStyle,
  textAlign: 'center',
  padding: '1rem',
}

const noveltyColors = {
  incremental: '#f59e0b',
  moderate: '#3b82f6',
  high: '#22c55e',
}

const difficultyColors = {
  low: '#22c55e',
  medium: '#f59e0b',
  high: '#ef4444',
}

export default function Report() {
  const [report, setReport] = useState(null)
  const [markdown, setMarkdown] = useState('')
  const [showMd, setShowMd] = useState(false)
  const navigate = useNavigate()

  useEffect(() => {
    fetch('/api/report').then(r => r.json()).then(setReport).catch(console.error)
    fetch('/api/report/md').then(r => r.text()).then(setMarkdown).catch(() => {})
  }, [])

  if (!report) return <p style={{ color: '#64748b' }}>Loading report...</p>

  const { stats, ideas } = report

  const handleRefine = (ideaId) => {
    fetch('/api/refine', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ idea_id: ideaId }),
    })
    navigate(`/refine/${ideaId}`)
  }

  const handleExport = () => {
    const blob = new Blob([markdown], { type: 'text/markdown' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'report.md'
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h1 style={{ fontSize: '1.5rem', fontWeight: 700 }}>Report</h1>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <button
            onClick={() => setShowMd(!showMd)}
            style={{
              padding: '0.5rem 1rem', background: '#334155', color: '#f1f5f9',
              border: 'none', borderRadius: '0.375rem', cursor: 'pointer', fontSize: '0.85rem',
            }}
          >
            {showMd ? 'Show Cards' : 'Show Markdown'}
          </button>
          {markdown && (
            <button
              onClick={handleExport}
              style={{
                padding: '0.5rem 1rem', background: '#475569', color: '#f1f5f9',
                border: 'none', borderRadius: '0.375rem', cursor: 'pointer', fontSize: '0.85rem',
              }}
            >
              Export MD
            </button>
          )}
        </div>
      </div>

      {/* Stats */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: '1rem' }}>
        <div style={statCardStyle}>
          <div style={{ fontSize: '2rem', fontWeight: 700, color: '#3b82f6' }}>{stats.total_papers}</div>
          <div style={{ fontSize: '0.8rem', color: '#94a3b8' }}>Total Papers</div>
        </div>
        <div style={statCardStyle}>
          <div style={{ fontSize: '2rem', fontWeight: 700, color: '#22c55e' }}>{stats.venue_papers}</div>
          <div style={{ fontSize: '0.8rem', color: '#94a3b8' }}>Top Venue</div>
        </div>
        <div style={statCardStyle}>
          <div style={{ fontSize: '2rem', fontWeight: 700, color: '#f59e0b' }}>{stats.velocity_papers}</div>
          <div style={{ fontSize: '0.8rem', color: '#94a3b8' }}>High Velocity</div>
        </div>
        <div style={statCardStyle}>
          <div style={{ fontSize: '2rem', fontWeight: 700, color: '#a855f7' }}>{stats.manual_papers}</div>
          <div style={{ fontSize: '0.8rem', color: '#94a3b8' }}>Manual</div>
        </div>
        <div style={statCardStyle}>
          <div style={{ fontSize: '2rem', fontWeight: 700, color: '#ec4899' }}>{stats.cluster_count}</div>
          <div style={{ fontSize: '0.8rem', color: '#94a3b8' }}>Clusters</div>
        </div>
      </div>

      {showMd ? (
        <div style={{ ...cardStyle, lineHeight: 1.7, fontSize: '0.95rem' }}>
          <ReactMarkdown>{markdown}</ReactMarkdown>
        </div>
      ) : (
        /* Idea Cards */
        <div>
          <h2 style={{ fontSize: '1.2rem', fontWeight: 600, marginBottom: '1rem' }}>Research Ideas</h2>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            {ideas.map(idea => (
              <div key={idea.id} style={cardStyle}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '0.75rem' }}>
                  <h3 style={{ fontSize: '1.05rem', fontWeight: 600 }}>{idea.title}</h3>
                  <div style={{ display: 'flex', gap: '0.5rem', flexShrink: 0 }}>
                    <span style={{
                      padding: '0.2rem 0.6rem', borderRadius: '0.25rem', fontSize: '0.7rem', fontWeight: 600,
                      background: noveltyColors[idea.novelty_assessment] || '#475569', color: '#fff',
                    }}>
                      {idea.novelty_assessment || 'N/A'}
                    </span>
                    <span style={{
                      padding: '0.2rem 0.6rem', borderRadius: '0.25rem', fontSize: '0.7rem', fontWeight: 600,
                      background: difficultyColors[idea.estimated_difficulty] || '#475569', color: '#fff',
                    }}>
                      {idea.estimated_difficulty || 'N/A'}
                    </span>
                    {idea.refined ? (
                      <span style={{
                        padding: '0.2rem 0.6rem', borderRadius: '0.25rem', fontSize: '0.7rem',
                        background: '#22c55e', color: '#fff', fontWeight: 600,
                      }}>
                        Refined
                      </span>
                    ) : null}
                  </div>
                </div>
                <p style={{ fontSize: '0.85rem', color: '#94a3b8', marginBottom: '0.5rem' }}>
                  <strong>Problem:</strong> {idea.problem_statement}
                </p>
                <p style={{ fontSize: '0.85rem', color: '#94a3b8', marginBottom: '1rem' }}>
                  <strong>Approach:</strong> {idea.proposed_approach}
                </p>
                <div style={{ display: 'flex', gap: '0.5rem' }}>
                  <button
                    onClick={() => handleRefine(idea.id)}
                    style={{
                      padding: '0.5rem 1rem', background: '#3b82f6', color: '#fff',
                      border: 'none', borderRadius: '0.375rem', cursor: 'pointer', fontSize: '0.85rem',
                    }}
                  >
                    Refine This Idea
                  </button>
                  <button
                    onClick={handleExport}
                    style={{
                      padding: '0.5rem 1rem', background: '#475569', color: '#f1f5f9',
                      border: 'none', borderRadius: '0.375rem', cursor: 'pointer', fontSize: '0.85rem',
                    }}
                  >
                    Export Markdown
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
