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

const mdStyles = {
  ...cardStyle,
  lineHeight: 1.8,
  fontSize: '0.95rem',
  overflowX: 'auto',
}

// Markdown 渲染样式覆盖
const markdownComponents = {
  h1: ({ children }) => <h1 style={{ fontSize: '1.6rem', fontWeight: 700, marginTop: '1.5rem', marginBottom: '0.75rem', borderBottom: '1px solid #334155', paddingBottom: '0.5rem' }}>{children}</h1>,
  h2: ({ children }) => <h2 style={{ fontSize: '1.3rem', fontWeight: 600, marginTop: '1.5rem', marginBottom: '0.5rem', color: '#e2e8f0' }}>{children}</h2>,
  h3: ({ children }) => <h3 style={{ fontSize: '1.1rem', fontWeight: 600, marginTop: '1rem', marginBottom: '0.5rem', color: '#cbd5e1' }}>{children}</h3>,
  p: ({ children }) => <p style={{ marginBottom: '0.75rem', color: '#94a3b8' }}>{children}</p>,
  strong: ({ children }) => <strong style={{ color: '#e2e8f0' }}>{children}</strong>,
  ul: ({ children }) => <ul style={{ paddingLeft: '1.5rem', marginBottom: '0.75rem', color: '#94a3b8' }}>{children}</ul>,
  ol: ({ children }) => <ol style={{ paddingLeft: '1.5rem', marginBottom: '0.75rem', color: '#94a3b8' }}>{children}</ol>,
  li: ({ children }) => <li style={{ marginBottom: '0.35rem' }}>{children}</li>,
  hr: () => <hr style={{ border: 'none', borderTop: '1px solid #334155', margin: '1.5rem 0' }} />,
  table: ({ children }) => (
    <div style={{ overflowX: 'auto', marginBottom: '1rem', border: '1px solid #334155', borderRadius: '0.5rem' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem', tableLayout: 'fixed', wordWrap: 'break-word' }}>{children}</table>
    </div>
  ),
  thead: ({ children }) => <thead style={{ background: '#0f172a' }}>{children}</thead>,
  th: ({ children }) => <th style={{ padding: '0.6rem 0.75rem', textAlign: 'left', fontWeight: 600, borderBottom: '2px solid #334155', color: '#e2e8f0', whiteSpace: 'nowrap' }}>{children}</th>,
  td: ({ children }) => <td style={{ padding: '0.6rem 0.75rem', borderBottom: '1px solid #1e293b', color: '#94a3b8', verticalAlign: 'top', lineHeight: 1.5, wordBreak: 'break-word' }}>{children}</td>,
  blockquote: ({ children }) => <blockquote style={{ borderLeft: '3px solid #3b82f6', paddingLeft: '1rem', margin: '0.75rem 0', color: '#94a3b8', fontStyle: 'italic' }}>{children}</blockquote>,
  code: ({ children, className }) => {
    if (className) {
      return <pre style={{ background: '#0f172a', padding: '1rem', borderRadius: '0.5rem', overflow: 'auto', fontSize: '0.85rem', marginBottom: '0.75rem' }}><code style={{ color: '#e2e8f0' }}>{children}</code></pre>
    }
    return <code style={{ background: '#0f172a', padding: '0.15rem 0.4rem', borderRadius: '0.25rem', fontSize: '0.85rem', color: '#60a5fa' }}>{children}</code>
  },
}

export default function Report() {
  const [report, setReport] = useState(null)
  const [markdown, setMarkdown] = useState('')
  const [showMd, setShowMd] = useState(false)
  const [history, setHistory] = useState([])
  const [selectedFile, setSelectedFile] = useState(null)
  const navigate = useNavigate()

  // 加载历史报告列表
  useEffect(() => {
    fetch('/api/reports').then(r => r.json()).then(setHistory).catch(() => {})
    fetch('/api/report').then(r => r.json()).then(setReport).catch(console.error)
    fetch('/api/report/md').then(r => r.ok ? r.text() : '').then(setMarkdown).catch(() => {})
  }, [])

  const loadReport = (filename) => {
    setSelectedFile(filename)
    fetch(`/api/report/md?filename=${encodeURIComponent(filename)}`)
      .then(r => r.text())
      .then(md => {
        setMarkdown(md)
        setShowMd(true)
      })
      .catch(console.error)
  }

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
    if (!markdown) return
    const blob = new Blob([markdown], { type: 'text/markdown' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = selectedFile || 'report.md'
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

      {/* History */}
      {history.length > 0 && (
        <div style={cardStyle}>
          <h2 style={{ fontSize: '1.1rem', marginBottom: '0.75rem' }}>Report History</h2>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
            {history.map(h => (
              <button
                key={h.filename}
                onClick={() => loadReport(h.filename)}
                style={{
                  padding: '0.4rem 0.8rem',
                  background: selectedFile === h.filename ? '#3b82f6' : '#0f172a',
                  color: selectedFile === h.filename ? '#fff' : '#94a3b8',
                  border: '1px solid #334155',
                  borderRadius: '0.375rem',
                  cursor: 'pointer',
                  fontSize: '0.8rem',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.5rem',
                }}
              >
                <span style={{
                  padding: '0.1rem 0.4rem',
                  background: '#1d4ed8',
                  color: '#fff',
                  borderRadius: '0.2rem',
                  fontSize: '0.7rem',
                  fontWeight: 600,
                }}>
                  {h.topic}
                </span>
                <span>{h.date}</span>
                <span style={{ color: '#475569' }}>{h.size_kb}KB</span>
              </button>
            ))}
          </div>
        </div>
      )}

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
        <div style={mdStyles}>
          <ReactMarkdown components={markdownComponents}>{markdown}</ReactMarkdown>
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
                  <div style={{ display: 'flex', gap: '0.5rem', flexShrink: 0, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
                    {/* Topic tag */}
                    {idea.topic && (
                      <span style={{
                        padding: '0.2rem 0.6rem', borderRadius: '0.25rem', fontSize: '0.7rem', fontWeight: 600,
                        background: '#1e3a5f', color: '#60a5fa', border: '1px solid #2563eb',
                      }}>
                        {idea.topic}
                      </span>
                    )}
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
                  <strong style={{ color: '#e2e8f0' }}>Problem:</strong> {idea.problem_statement}
                </p>
                <p style={{ fontSize: '0.85rem', color: '#94a3b8', marginBottom: '1rem' }}>
                  <strong style={{ color: '#e2e8f0' }}>Approach:</strong> {idea.proposed_approach}
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
            {ideas.length === 0 && (
              <p style={{ color: '#64748b' }}>No ideas yet. Run the pipeline first.</p>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
