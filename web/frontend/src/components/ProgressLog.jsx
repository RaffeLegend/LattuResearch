import React, { useEffect, useRef } from 'react'

const stepColors = {
  collector: '#3b82f6',
  downloader: '#8b5cf6',
  extractor: '#ec4899',
  embedder: '#f59e0b',
  analyst: '#22c55e',
  refiner: '#06b6d4',
  error: '#ef4444',
}

export default function ProgressLog({ logs, running, onEvent }) {
  const logEndRef = useRef(null)
  const eventSourceRef = useRef(null)

  useEffect(() => {
    if (!running) {
      if (eventSourceRef.current) {
        eventSourceRef.current.close()
        eventSourceRef.current = null
      }
      return
    }

    const es = new EventSource('/api/progress')
    eventSourceRef.current = es

    es.addEventListener('progress', (e) => {
      try {
        const data = JSON.parse(e.data)
        onEvent(data)
      } catch {}
    })

    es.onerror = () => {
      es.close()
    }

    return () => {
      es.close()
    }
  }, [running])

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [logs])

  // Calculate overall progress
  const latestProgress = logs.length > 0 ? logs[logs.length - 1] : null
  const steps = ['collector', 'downloader', 'extractor', 'embedder', 'analyst']
  const currentStepIdx = latestProgress ? steps.indexOf(latestProgress.step) : -1
  const overallProgress = latestProgress
    ? Math.round(((currentStepIdx >= 0 ? currentStepIdx : 0) / steps.length) * 100 +
        (latestProgress.progress / steps.length))
    : 0

  return (
    <div>
      {/* Progress bar */}
      <div style={{
        height: '6px', borderRadius: '3px', background: '#0f172a',
        marginBottom: '1rem', overflow: 'hidden',
      }}>
        <div style={{
          height: '100%', borderRadius: '3px',
          width: `${Math.min(100, overallProgress)}%`,
          background: 'linear-gradient(90deg, #3b82f6, #22c55e)',
          transition: 'width 0.3s ease',
        }} />
      </div>

      {/* Step indicators */}
      <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1rem' }}>
        {steps.map((step, i) => {
          let status = 'pending'
          const stepLogs = logs.filter(l => l.step === step)
          if (stepLogs.some(l => l.status === 'done')) status = 'done'
          else if (stepLogs.some(l => l.status === 'running')) status = 'running'
          else if (stepLogs.some(l => l.status === 'error')) status = 'error'

          return (
            <div key={step} style={{
              flex: 1, textAlign: 'center', padding: '0.5rem',
              borderRadius: '0.375rem', fontSize: '0.75rem', fontWeight: 500,
              background: status === 'done' ? '#064e3b' :
                status === 'running' ? '#1e3a5f' :
                status === 'error' ? '#7f1d1d' : '#1e293b',
              color: status === 'done' ? '#34d399' :
                status === 'running' ? '#60a5fa' :
                status === 'error' ? '#fca5a5' : '#475569',
              border: `1px solid ${status === 'running' ? '#3b82f6' : 'transparent'}`,
            }}>
              {step}
            </div>
          )
        })}
      </div>

      {/* Log entries */}
      <div style={{
        maxHeight: '300px', overflowY: 'auto', fontFamily: 'monospace',
        fontSize: '0.8rem', background: '#0f172a', borderRadius: '0.5rem',
        padding: '1rem',
      }}>
        {logs.length === 0 && (
          <div style={{ color: '#475569' }}>
            {running ? 'Waiting for events...' : 'No logs yet. Start the pipeline to see progress.'}
          </div>
        )}
        {logs.map((log, i) => (
          <div key={i} style={{
            padding: '0.25rem 0',
            color: log.status === 'error' ? '#fca5a5' : stepColors[log.step] || '#94a3b8',
          }}>
            <span style={{ color: '#475569' }}>[{log.step}]</span>{' '}
            {log.message}
          </div>
        ))}
        <div ref={logEndRef} />
      </div>
    </div>
  )
}
