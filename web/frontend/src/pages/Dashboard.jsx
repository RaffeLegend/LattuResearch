import React, { useState, useRef } from 'react'
import ProgressLog from '../components/ProgressLog'

const inputStyle = {
  padding: '0.75rem 1rem',
  background: '#1e293b',
  border: '1px solid #334155',
  borderRadius: '0.5rem',
  color: '#f1f5f9',
  fontSize: '1rem',
  width: '100%',
}

const btnStyle = {
  padding: '0.75rem 2rem',
  background: '#3b82f6',
  color: '#fff',
  border: 'none',
  borderRadius: '0.5rem',
  fontWeight: 600,
  cursor: 'pointer',
  fontSize: '1rem',
}

const cardStyle = {
  background: '#1e293b',
  borderRadius: '0.75rem',
  padding: '1.5rem',
  border: '1px solid #334155',
}

export default function Dashboard() {
  const [topic, setTopic] = useState('')
  const [months, setMonths] = useState(6)
  const [arxivIds, setArxivIds] = useState('')
  const [manualPapers, setManualPapers] = useState([])
  const [running, setRunning] = useState(false)
  const [logs, setLogs] = useState([])
  const fileInputRef = useRef(null)

  const addArxivIds = () => {
    if (!arxivIds.trim()) return
    const ids = arxivIds.split(',').map(id => id.trim()).filter(Boolean)
    setManualPapers(prev => [...prev, ...ids.map(id => ({ type: 'arxiv', value: id }))])
    setArxivIds('')
  }

  const handleFileUpload = (e) => {
    const files = Array.from(e.target.files)
    files.forEach(f => {
      if (f.name.endsWith('.pdf')) {
        setManualPapers(prev => [...prev, { type: 'pdf', value: f.name, file: f }])
      }
    })
  }

  const removePaper = (index) => {
    setManualPapers(prev => prev.filter((_, i) => i !== index))
  }

  const handleRun = async () => {
    if (!topic.trim()) return
    setRunning(true)
    setLogs([])

    // Upload manual papers first
    if (manualPapers.length > 0) {
      const arxivList = manualPapers.filter(p => p.type === 'arxiv').map(p => p.value)
      const pdfFiles = manualPapers.filter(p => p.type === 'pdf' && p.file)

      if (arxivList.length > 0 || pdfFiles.length > 0) {
        const formData = new FormData()
        if (arxivList.length > 0) {
          formData.append('arxiv_ids', arxivList.join(','))
        }
        pdfFiles.forEach(p => formData.append('files', p.file))
        await fetch('/api/upload', { method: 'POST', body: formData })
      }
    }

    // Start pipeline
    try {
      await fetch('/api/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ topic, time_range_months: months }),
      })
    } catch (e) {
      setLogs(prev => [...prev, { step: 'error', status: 'error', message: e.message, progress: 0 }])
      setRunning(false)
    }
  }

  const handleLogEvent = (event) => {
    setLogs(prev => [...prev, event])
    if (event.status === 'done' && event.step === 'analyst') {
      setRunning(false)
    }
    if (event.status === 'error') {
      setRunning(false)
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      <h1 style={{ fontSize: '1.5rem', fontWeight: 700 }}>Dashboard</h1>

      <div style={cardStyle}>
        <h2 style={{ marginBottom: '1rem', fontSize: '1.1rem' }}>Research Topic</h2>
        <div style={{ display: 'flex', gap: '1rem', alignItems: 'flex-end' }}>
          <div style={{ flex: 1 }}>
            <input
              style={inputStyle}
              placeholder="e.g., offline reinforcement learning"
              value={topic}
              onChange={e => setTopic(e.target.value)}
              disabled={running}
            />
          </div>
          <div>
            <select
              style={{ ...inputStyle, width: 'auto' }}
              value={months}
              onChange={e => setMonths(Number(e.target.value))}
              disabled={running}
            >
              <option value={3}>3 months</option>
              <option value={6}>6 months</option>
              <option value={12}>1 year</option>
            </select>
          </div>
          <button
            style={{ ...btnStyle, opacity: running ? 0.5 : 1 }}
            onClick={handleRun}
            disabled={running || !topic.trim()}
          >
            {running ? 'Running...' : 'Run Pipeline'}
          </button>
        </div>
      </div>

      <div style={cardStyle}>
        <h2 style={{ marginBottom: '1rem', fontSize: '1.1rem' }}>Manual Papers</h2>
        <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1rem' }}>
          <input
            style={{ ...inputStyle, flex: 1 }}
            placeholder="arXiv IDs (comma separated, e.g., 2401.12345, 2402.00001)"
            value={arxivIds}
            onChange={e => setArxivIds(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && addArxivIds()}
          />
          <button style={{ ...btnStyle, background: '#475569' }} onClick={addArxivIds}>Add</button>
        </div>

        <div
          style={{
            border: '2px dashed #475569', borderRadius: '0.5rem', padding: '1.5rem',
            textAlign: 'center', cursor: 'pointer', marginBottom: '1rem',
          }}
          onClick={() => fileInputRef.current?.click()}
          onDragOver={e => e.preventDefault()}
          onDrop={e => {
            e.preventDefault()
            const files = Array.from(e.dataTransfer.files)
            files.forEach(f => {
              if (f.name.endsWith('.pdf'))
                setManualPapers(prev => [...prev, { type: 'pdf', value: f.name, file: f }])
            })
          }}
        >
          <p style={{ color: '#64748b' }}>Drop PDF files here or click to upload</p>
          <input ref={fileInputRef} type="file" accept=".pdf" multiple hidden onChange={handleFileUpload} />
        </div>

        {manualPapers.length > 0 && (
          <ul style={{ listStyle: 'none', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            {manualPapers.map((p, i) => (
              <li key={i} style={{
                display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                padding: '0.5rem 0.75rem', background: '#0f172a', borderRadius: '0.375rem',
              }}>
                <span>
                  <span style={{
                    display: 'inline-block', padding: '0.125rem 0.5rem', borderRadius: '0.25rem',
                    fontSize: '0.75rem', marginRight: '0.5rem',
                    background: p.type === 'arxiv' ? '#1d4ed8' : '#7c3aed',
                  }}>
                    {p.type.toUpperCase()}
                  </span>
                  {p.value}
                </span>
                <button
                  onClick={() => removePaper(i)}
                  style={{ background: 'none', border: 'none', color: '#ef4444', cursor: 'pointer' }}
                >
                  Remove
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div style={cardStyle}>
        <h2 style={{ marginBottom: '1rem', fontSize: '1.1rem' }}>Progress</h2>
        <ProgressLog logs={logs} running={running} onEvent={handleLogEvent} />
      </div>
    </div>
  )
}
