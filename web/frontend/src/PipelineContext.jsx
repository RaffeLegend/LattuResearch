import React, { createContext, useContext, useState, useEffect, useRef, useCallback } from 'react'

const PipelineContext = createContext(null)

export function usePipeline() {
  return useContext(PipelineContext)
}

export function PipelineProvider({ children }) {
  const [running, setRunning] = useState(false)
  const [logs, setLogs] = useState([])
  const [topic, setTopic] = useState('')
  const [pipelineType, setPipelineType] = useState(null)
  const eventSourceRef = useRef(null)
  const runningRef = useRef(false)

  // Keep ref in sync
  useEffect(() => {
    runningRef.current = running
  }, [running])

  const disconnectSSE = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close()
      eventSourceRef.current = null
    }
  }, [])

  const connectSSE = useCallback(() => {
    // Close existing first
    disconnectSSE()

    const es = new EventSource('/api/progress')
    eventSourceRef.current = es

    es.addEventListener('progress', (e) => {
      try {
        const data = JSON.parse(e.data)
        setLogs(prev => [...prev, data])

        if (data.status === 'done' && (data.step === 'analyst' || data.step === 'refiner')) {
          setRunning(false)
          // Don't disconnect immediately - let remaining events drain
          setTimeout(() => disconnectSSE(), 2000)
        }
        if (data.status === 'error') {
          setRunning(false)
          setTimeout(() => disconnectSSE(), 2000)
        }
      } catch {}
    })

    es.onerror = () => {
      disconnectSSE()
      // Use ref to avoid stale closure
      if (runningRef.current) {
        setTimeout(() => {
          if (runningRef.current) connectSSE()
        }, 2000)
      }
    }
  }, [disconnectSSE])

  // Cleanup on unmount
  useEffect(() => {
    return () => disconnectSSE()
  }, [disconnectSSE])

  const startPipeline = useCallback(async (topicName, months, manualPapers = []) => {
    setRunning(true)
    setLogs([])
    setTopic(topicName)
    setPipelineType('pipeline')

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

    // Connect SSE before starting pipeline
    connectSSE()

    try {
      const res = await fetch('/api/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ topic: topicName, time_range_months: months }),
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Failed to start pipeline' }))
        setLogs(prev => [...prev, { step: 'error', status: 'error', message: err.detail, progress: 0 }])
        setRunning(false)
        disconnectSSE()
      }
    } catch (e) {
      setLogs(prev => [...prev, { step: 'error', status: 'error', message: e.message, progress: 0 }])
      setRunning(false)
      disconnectSSE()
    }
  }, [connectSSE, disconnectSSE])

  const startRefine = useCallback(async (ideaId) => {
    setRunning(true)
    setLogs([])
    setPipelineType('refine')

    connectSSE()

    try {
      const res = await fetch('/api/refine', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ idea_id: ideaId }),
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Failed to start refinement' }))
        setLogs(prev => [...prev, { step: 'error', status: 'error', message: err.detail, progress: 0 }])
        setRunning(false)
        disconnectSSE()
      }
    } catch (e) {
      setLogs(prev => [...prev, { step: 'error', status: 'error', message: e.message, progress: 0 }])
      setRunning(false)
      disconnectSSE()
    }
  }, [connectSSE, disconnectSSE])

  return (
    <PipelineContext.Provider value={{
      running, logs, topic, pipelineType,
      startPipeline, startRefine,
    }}>
      {children}
    </PipelineContext.Provider>
  )
}
