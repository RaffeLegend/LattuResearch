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

  useEffect(() => {
    fetch('/api/clusters')
      .then(r => r.json())
      .then(setData)
      .catch(console.error)
  }, [])

  if (!data) return <p style={{ color: '#64748b' }}>Loading cluster data...</p>

  const { clusters, points } = data

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      <h1 style={{ fontSize: '1.5rem', fontWeight: 700 }}>Overview</h1>

      <div style={{ display: 'grid', gridTemplateColumns: '250px 1fr 300px', gap: '1.5rem' }}>
        {/* Left: Cluster list */}
        <div style={cardStyle}>
          <h3 style={{ marginBottom: '1rem', fontSize: '0.95rem', color: '#94a3b8' }}>Clusters</h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            {clusters.map(c => {
              const trend = trendIcons[c.trend] || trendIcons.stable
              const isSelected = selectedCluster === c.id
              return (
                <div
                  key={c.id}
                  onClick={() => setSelectedCluster(isSelected ? null : c.id)}
                  style={{
                    padding: '0.75rem',
                    borderRadius: '0.5rem',
                    cursor: 'pointer',
                    background: isSelected ? '#334155' : 'transparent',
                    border: isSelected ? '1px solid #475569' : '1px solid transparent',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ fontSize: '0.85rem', fontWeight: 500 }}>{c.name}</span>
                    <span style={{ fontSize: '0.75rem', color: trend.color }}>
                      {trend.icon} {trend.label}
                    </span>
                  </div>
                  <span style={{ fontSize: '0.75rem', color: '#64748b' }}>{c.paper_count} papers</span>
                </div>
              )
            })}
          </div>
        </div>

        {/* Center: UMAP scatter plot */}
        <div style={cardStyle}>
          <h3 style={{ marginBottom: '1rem', fontSize: '0.95rem', color: '#94a3b8' }}>UMAP Scatter Plot</h3>
          <ClusterMap
            points={points}
            clusters={clusters}
            selectedCluster={selectedCluster}
          />
        </div>

        {/* Right: Time heatmap */}
        <div style={cardStyle}>
          <h3 style={{ marginBottom: '1rem', fontSize: '0.95rem', color: '#94a3b8' }}>Time Distribution</h3>
          <div style={{ fontSize: '0.8rem', color: '#64748b' }}>
            {clusters.map(c => {
              const trend = trendIcons[c.trend] || trendIcons.stable
              return (
                <div key={c.id} style={{ marginBottom: '0.75rem' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.25rem' }}>
                    <span>{c.name}</span>
                    <span>{c.paper_count}</span>
                  </div>
                  <div style={{
                    height: '8px', borderRadius: '4px', background: '#0f172a', overflow: 'hidden',
                  }}>
                    <div style={{
                      height: '100%', borderRadius: '4px',
                      width: `${Math.min(100, (c.paper_count / Math.max(...clusters.map(x => x.paper_count))) * 100)}%`,
                      background: trend.color,
                    }} />
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      </div>
    </div>
  )
}
