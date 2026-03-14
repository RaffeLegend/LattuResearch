import React from 'react'

const passedByBadge = {
  venue: { bg: '#1d4ed8', label: 'Top Venue' },
  velocity: { bg: '#b45309', label: 'High Velocity' },
  'venue+velocity': { bg: '#7c3aed', label: 'Venue + Velocity' },
  manual: { bg: '#059669', label: 'Manual' },
}

export default function PaperCard({ paper }) {
  const badge = passedByBadge[paper.passed_by] || passedByBadge.venue

  return (
    <div style={{
      background: '#1e293b',
      borderRadius: '0.5rem',
      padding: '1rem',
      border: '1px solid #334155',
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '0.5rem' }}>
        <h4 style={{ fontSize: '0.9rem', fontWeight: 500, flex: 1, marginRight: '0.5rem' }}>
          {paper.title}
        </h4>
        <span style={{
          padding: '0.15rem 0.5rem',
          borderRadius: '0.25rem',
          fontSize: '0.7rem',
          fontWeight: 600,
          background: badge.bg,
          color: '#fff',
          whiteSpace: 'nowrap',
        }}>
          {badge.label}
        </span>
      </div>

      <div style={{ display: 'flex', gap: '1rem', fontSize: '0.75rem', color: '#64748b' }}>
        {paper.venue && <span>Venue: {paper.venue}</span>}
        <span>Citations: {paper.citation_count || 0}</span>
        <span>Velocity: {(paper.citation_velocity || 0).toFixed(2)}/day</span>
        <span>{paper.published_date}</span>
      </div>

      {paper.arxiv_url && (
        <a
          href={paper.arxiv_url}
          target="_blank"
          rel="noopener noreferrer"
          style={{ fontSize: '0.75rem', color: '#3b82f6', textDecoration: 'none' }}
        >
          arXiv
        </a>
      )}
    </div>
  )
}
