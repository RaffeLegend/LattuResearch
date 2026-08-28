import React, { useEffect, useState } from 'react'
import ClusterMap from '../components/ClusterMap'

const cardStyle = {
  background: '#1e293b',
  borderRadius: '0.75rem',
  padding: '1.5rem',
  border: '1px solid #334155',
}

const trendIcons = {
  hot: { icon: '\uD83D\uDD25', label: 'Hot', color: '#ef4444' },
  emerging: { icon: '\uD83D\uDE80', label: 'Emerging', color: '#22c55e' },
  declining: { icon: '\uD83D\uDCC9', label: 'Declining', color: '#f59e0b' },
  stable: { icon: '\uD83D\uDCCA', label: 'Stable', color: '#3b82f6' },
}

export default function Overview() {
  const [data, setData] = useState(null)
  const [selectedCluster, setSelectedCluster] = useState(null)
  const [papers, setPapers] = useState([])

  useEffect(() => {
    fetch('/api/clusters')
      .then(r => r.json())
      .then(setData)
      .catch(console.error)
    fetch('/api/papers')
      .then(r => r.json())
      .then(setPapers)
      .catch(console.error)
  }, [])

  if (!data) return <p style={{ color: '#64748b' }}>Loading cluster data...</p>

  const { clusters, points } = data

  // Get papers in selected cluster
  const selectedClusterInfo = clusters.find(c => c.id === selectedCluster)
  const clusterPaperIds = selectedCluster
    ? points.filter(p => p.cluster_id === selectedCluster).map(p => p.paper_id)
    : []
  const clusterPapers = papers.filter(p => clusterPaperIds.includes(p.id))

  // Stats
  const totalPapers = papers.length
  const venuePapers = papers.filter(p => (p.passed_by || '').includes('venue')).length
  const velocityPapers = papers.filter(p => (p.passed_by || '').includes('velocity')).length
  const recentPapers = papers.filter(p => p.passed_by === 'recent').length

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h1 style={{ fontSize: '1.5rem', fontWeight: 700 }}>Overview</h1>
        <div style={{ display: 'flex', gap: '0.75rem', fontSize: '0.8rem', color: '#94a3b8' }}>
          <span>{totalPapers} papers</span>
          <span style={{ color: '#334155' }}>|</span>
          <span>{clusters.length} clusters</span>
          <span style={{ color: '#334155' }}>|</span>
          <span style={{ color: '#22c55e' }}>{venuePapers} venue</span>
          <span style={{ color: '#f59e0b' }}>{velocityPapers} velocity</span>
          <span style={{ color: '#60a5fa' }}>{recentPapers} recent</span>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '240px 1fr', gap: '1.5rem' }}>
        {/* Left: Cluster list */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <div style={cardStyle}>
            <h3 style={{ marginBottom: '0.75rem', fontSize: '0.9rem', color: '#94a3b8' }}>Clusters</h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
              {clusters.map(c => {
                const trend = trendIcons[c.trend] || trendIcons.stable
                const isSelected = selectedCluster === c.id
                return (
                  <div
                    key={c.id}
                    onClick={() => setSelectedCluster(isSelected ? null : c.id)}
                    style={{
                      padding: '0.6rem 0.75rem',
                      borderRadius: '0.375rem',
                      cursor: 'pointer',
                      background: isSelected ? '#334155' : 'transparent',
                      border: isSelected ? '1px solid #475569' : '1px solid transparent',
                      transition: 'background 0.15s',
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span style={{ fontSize: '0.8rem', fontWeight: 500, lineHeight: 1.3 }}>{c.name}</span>
                    </div>
                    <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.25rem', alignItems: 'center' }}>
                      <span style={{ fontSize: '0.7rem', color: trend.color }}>
                        {trend.icon} {trend.label}
                      </span>
                      <span style={{ fontSize: '0.7rem', color: '#475569' }}>|</span>
                      <span style={{ fontSize: '0.7rem', color: '#64748b' }}>{c.paper_count} papers</span>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>

          {/* Shape legend */}
          <div style={{ ...cardStyle, padding: '1rem' }}>
            <h3 style={{ marginBottom: '0.5rem', fontSize: '0.8rem', color: '#64748b' }}>Point Shapes</h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem', fontSize: '0.75rem', color: '#94a3b8' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <svg width="14" height="14"><circle cx="7" cy="7" r="5" fill="#94a3b8" /></svg>
                <span>Top Venue / Recent</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <svg width="14" height="14"><polygon points="7,2 12,12 2,12" fill="#94a3b8" /></svg>
                <span>High Velocity</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <svg width="14" height="14"><polygon points="7,1 8.5,5 13,5.5 9.5,8.5 10.5,13 7,10.5 3.5,13 4.5,8.5 1,5.5 5.5,5" fill="#94a3b8" /></svg>
                <span>Manual</span>
              </div>
            </div>
          </div>
        </div>

        {/* Right: Main content */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
          {/* Scatter plot */}
          <div style={cardStyle}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
              <h3 style={{ fontSize: '0.95rem', color: '#94a3b8' }}>UMAP Cluster Map</h3>
              {selectedCluster && selectedClusterInfo && (
                <button
                  onClick={() => setSelectedCluster(null)}
                  style={{
                    padding: '0.3rem 0.6rem', background: '#334155', color: '#94a3b8',
                    border: 'none', borderRadius: '0.25rem', cursor: 'pointer', fontSize: '0.75rem',
                  }}
                >
                  Clear filter: {selectedClusterInfo.name}
                </button>
              )}
            </div>
            <ClusterMap
              points={points}
              clusters={clusters}
              selectedCluster={selectedCluster}
              onSelectCluster={setSelectedCluster}
            />
          </div>

          {/* Selected cluster detail */}
          {selectedCluster && selectedClusterInfo && (
            <div style={cardStyle}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
                <h3 style={{ fontSize: '1rem', fontWeight: 600 }}>{selectedClusterInfo.name}</h3>
                <span style={{ fontSize: '0.8rem', color: (trendIcons[selectedClusterInfo.trend] || trendIcons.stable).color }}>
                  {(trendIcons[selectedClusterInfo.trend] || trendIcons.stable).icon} {(trendIcons[selectedClusterInfo.trend] || trendIcons.stable).label}
                </span>
              </div>
              {selectedClusterInfo.summary && (
                <p style={{ fontSize: '0.85rem', color: '#94a3b8', marginBottom: '1rem', lineHeight: 1.6 }}>
                  {selectedClusterInfo.summary}
                </p>
              )}
              <h4 style={{ fontSize: '0.85rem', color: '#64748b', marginBottom: '0.5rem' }}>
                Papers in this cluster ({clusterPapers.length})
              </h4>
              <div style={{ maxHeight: '300px', overflowY: 'auto' }}>
                {clusterPapers.map(p => (
                  <div key={p.id} style={{
                    padding: '0.5rem 0.75rem',
                    background: '#0f172a',
                    borderRadius: '0.375rem',
                    marginBottom: '0.375rem',
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                  }}>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: '0.82rem', fontWeight: 500, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                        {p.title}
                      </div>
                      <div style={{ fontSize: '0.72rem', color: '#64748b', marginTop: '0.15rem' }}>
                        {p.venue || 'arXiv'} | {p.published_date} | citations: {p.citation_count || 0}
                      </div>
                    </div>
                    <span style={{
                      padding: '0.15rem 0.4rem', borderRadius: '0.2rem', fontSize: '0.65rem',
                      fontWeight: 600, flexShrink: 0, marginLeft: '0.5rem',
                      background: p.passed_by === 'venue' ? '#064e3b' : p.passed_by === 'velocity' ? '#78350f' : '#1e3a5f',
                      color: p.passed_by === 'venue' ? '#34d399' : p.passed_by === 'velocity' ? '#fbbf24' : '#60a5fa',
                    }}>
                      {p.passed_by}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
