import React, { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import ProgressLog from '../components/ProgressLog'

const cardStyle = {
  background: '#1e293b',
  borderRadius: '0.75rem',
  padding: '1.5rem',
  border: '1px solid #334155',
}

export default function IdeaRefine() {
  const { ideaId } = useParams()
  const [ideas, setIdeas] = useState([])
  const [selectedId, setSelectedId] = useState(ideaId ? Number(ideaId) : null)
  const [refinement, setRefinement] = useState(null)
  const [logs, setLogs] = useState([])
  const [running, setRunning] = useState(!!ideaId)

  useEffect(() => {
    fetch('/api/ideas').then(r => r.json()).then(setIdeas).catch(console.error)
  }, [])

  useEffect(() => {
    if (selectedId) {
      fetch(`/api/refinement/${selectedId}`)
        .then(r => r.ok ? r.json() : null)
        .then(data => { if (data) setRefinement(data) })
        .catch(() => {})
    }
  }, [selectedId, running])

  const handleRefine = async (id) => {
    setSelectedId(id)
    setRunning(true)
    setLogs([])
    await fetch('/api/refine', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ idea_id: id }),
    })
  }

  const handleLogEvent = (event) => {
    setLogs(prev => [...prev, event])
    if (event.status === 'done' || event.status === 'error') {
      setRunning(false)
      // Refresh refinement data
      if (selectedId) {
        fetch(`/api/refinement/${selectedId}`)
          .then(r => r.ok ? r.json() : null)
          .then(data => { if (data) setRefinement(data) })
          .catch(() => {})
      }
    }
  }

  const selectedIdea = ideas.find(i => i.id === selectedId)

  const handleExport = () => {
    if (!refinement?.refinement?.report_md) return
    const blob = new Blob([refinement.refinement.report_md], { type: 'text/markdown' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `idea-${selectedId}-refinement.md`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      <h1 style={{ fontSize: '1.5rem', fontWeight: 700 }}>Idea Refinement</h1>

      {/* Idea selector */}
      {!selectedId && (
        <div style={cardStyle}>
          <h2 style={{ fontSize: '1.1rem', marginBottom: '1rem' }}>Select an Idea to Refine</h2>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            {ideas.map(idea => (
              <div
                key={idea.id}
                style={{
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                  padding: '1rem', background: '#0f172a', borderRadius: '0.5rem',
                }}
              >
                <div>
                  <div style={{ fontWeight: 500, marginBottom: '0.25rem' }}>{idea.title}</div>
                  <div style={{ fontSize: '0.8rem', color: '#64748b' }}>{idea.problem_statement}</div>
                </div>
                <button
                  onClick={() => handleRefine(idea.id)}
                  disabled={idea.refined}
                  style={{
                    padding: '0.5rem 1rem', flexShrink: 0,
                    background: idea.refined ? '#334155' : '#3b82f6',
                    color: '#fff', border: 'none', borderRadius: '0.375rem',
                    cursor: idea.refined ? 'default' : 'pointer', fontSize: '0.85rem',
                  }}
                >
                  {idea.refined ? 'Already Refined' : 'Refine'}
                </button>
              </div>
            ))}
            {ideas.length === 0 && (
              <p style={{ color: '#64748b' }}>No ideas yet. Run the pipeline first.</p>
            )}
          </div>
        </div>
      )}

      {/* Selected idea details */}
      {selectedIdea && (
        <div style={cardStyle}>
          <h2 style={{ fontSize: '1.1rem', marginBottom: '1rem' }}>Original Idea</h2>
          <h3 style={{ fontWeight: 600, marginBottom: '0.5rem' }}>{selectedIdea.title}</h3>
          <p style={{ fontSize: '0.9rem', color: '#94a3b8', marginBottom: '0.5rem' }}>
            <strong>Problem:</strong> {selectedIdea.problem_statement}
          </p>
          <p style={{ fontSize: '0.9rem', color: '#94a3b8', marginBottom: '0.5rem' }}>
            <strong>Approach:</strong> {selectedIdea.proposed_approach}
          </p>
          <p style={{ fontSize: '0.9rem', color: '#94a3b8' }}>
            <strong>Hypothesis:</strong> {selectedIdea.key_hypothesis}
          </p>
        </div>
      )}

      {/* Progress */}
      {running && (
        <div style={cardStyle}>
          <h2 style={{ fontSize: '1.1rem', marginBottom: '1rem' }}>Refinement Progress</h2>
          <ProgressLog logs={logs} running={running} onEvent={handleLogEvent} />
        </div>
      )}

      {/* Refinement result */}
      {refinement && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          {/* Closest existing work */}
          {refinement.refinement.closest_existing_work && (
            <div style={cardStyle}>
              <h2 style={{ fontSize: '1.1rem', marginBottom: '1rem' }}>Closest Existing Work</h2>
              {JSON.parse(refinement.refinement.closest_existing_work || '[]').map((w, i) => (
                <div key={i} style={{ padding: '0.75rem', background: '#0f172a', borderRadius: '0.5rem', marginBottom: '0.5rem' }}>
                  <div style={{ fontWeight: 500 }}>{w.title} <span style={{ color: '#64748b', fontSize: '0.8rem' }}>({w.venue})</span></div>
                  <div style={{ fontSize: '0.85rem', color: '#94a3b8', marginTop: '0.25rem' }}>
                    Similarity: {w.similarity} | Difference: {w.key_difference}
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Detailed sections */}
          <div style={cardStyle}>
            <h2 style={{ fontSize: '1.1rem', marginBottom: '1rem' }}>Overlap Analysis</h2>
            <p style={{ fontSize: '0.9rem', color: '#94a3b8' }}>{refinement.refinement.overlap_analysis}</p>
          </div>

          <div style={cardStyle}>
            <h2 style={{ fontSize: '1.1rem', marginBottom: '1rem' }}>Refined Technical Approach</h2>
            <p style={{ fontSize: '0.9rem', color: '#94a3b8' }}>{refinement.refinement.method_detail}</p>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
            <div style={cardStyle}>
              <h3 style={{ fontSize: '1rem', marginBottom: '0.75rem' }}>Recommended Baselines</h3>
              <ul style={{ paddingLeft: '1.25rem', fontSize: '0.85rem', color: '#94a3b8' }}>
                {JSON.parse(refinement.refinement.recommended_baselines || '[]').map((b, i) => (
                  <li key={i} style={{ marginBottom: '0.25rem' }}>{b}</li>
                ))}
              </ul>
            </div>
            <div style={cardStyle}>
              <h3 style={{ fontSize: '1rem', marginBottom: '0.75rem' }}>Recommended Datasets</h3>
              <ul style={{ paddingLeft: '1.25rem', fontSize: '0.85rem', color: '#94a3b8' }}>
                {JSON.parse(refinement.refinement.recommended_datasets || '[]').map((d, i) => (
                  <li key={i} style={{ marginBottom: '0.25rem' }}>{d}</li>
                ))}
              </ul>
            </div>
          </div>

          <div style={cardStyle}>
            <h2 style={{ fontSize: '1.1rem', marginBottom: '1rem' }}>MVP Experiment</h2>
            <p style={{ fontSize: '0.9rem', color: '#94a3b8' }}>{refinement.refinement.mvp_experiment}</p>
          </div>

          <div style={cardStyle}>
            <h2 style={{ fontSize: '1.1rem', marginBottom: '1rem' }}>Feasibility Assessment</h2>
            <p style={{ fontSize: '0.9rem', color: '#94a3b8' }}>{refinement.refinement.feasibility_assessment}</p>
          </div>

          <div style={cardStyle}>
            <h2 style={{ fontSize: '1.1rem', marginBottom: '1rem' }}>Updated Risks</h2>
            <ul style={{ paddingLeft: '1.25rem', fontSize: '0.85rem', color: '#94a3b8' }}>
              {JSON.parse(refinement.refinement.updated_risks || '[]').map((r, i) => (
                <li key={i} style={{ marginBottom: '0.25rem' }}>{r}</li>
              ))}
            </ul>
          </div>

          {/* Export */}
          <button
            onClick={handleExport}
            style={{
              padding: '0.75rem 2rem', background: '#3b82f6', color: '#fff',
              border: 'none', borderRadius: '0.5rem', cursor: 'pointer',
              fontSize: '1rem', fontWeight: 600, alignSelf: 'flex-start',
            }}
          >
            Export Refinement Report
          </button>
        </div>
      )}
    </div>
  )
}
