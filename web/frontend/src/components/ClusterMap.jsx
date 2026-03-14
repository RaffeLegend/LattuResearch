import React, { useEffect, useRef } from 'react'
import * as d3 from 'd3'

const shapeForPassedBy = (passedBy) => {
  if (!passedBy) return 'circle'
  if (passedBy.includes('manual')) return 'star'
  if (passedBy.includes('velocity')) return 'triangle'
  return 'circle' // venue
}

export default function ClusterMap({ points, clusters, selectedCluster }) {
  const svgRef = useRef(null)

  useEffect(() => {
    if (!points || points.length === 0) return

    const svg = d3.select(svgRef.current)
    svg.selectAll('*').remove()

    const width = 600
    const height = 450
    const margin = { top: 20, right: 20, bottom: 20, left: 20 }
    const innerW = width - margin.left - margin.right
    const innerH = height - margin.top - margin.bottom

    const g = svg
      .attr('viewBox', `0 0 ${width} ${height}`)
      .append('g')
      .attr('transform', `translate(${margin.left},${margin.top})`)

    // Scales
    const xExtent = d3.extent(points, d => d.umap_x)
    const yExtent = d3.extent(points, d => d.umap_y)
    const x = d3.scaleLinear().domain(xExtent).range([0, innerW]).nice()
    const y = d3.scaleLinear().domain(yExtent).range([innerH, 0]).nice()

    // Color scale by cluster
    const clusterIds = [...new Set(points.map(d => d.cluster_id))]
    const color = d3.scaleOrdinal(d3.schemeTableau10).domain(clusterIds)

    // Tooltip
    const tooltip = d3.select('body').append('div')
      .style('position', 'absolute')
      .style('background', '#1e293b')
      .style('border', '1px solid #475569')
      .style('border-radius', '6px')
      .style('padding', '8px 12px')
      .style('font-size', '12px')
      .style('color', '#e2e8f0')
      .style('pointer-events', 'none')
      .style('opacity', 0)
      .style('z-index', 1000)

    // Draw points
    const nodes = g.selectAll('.point')
      .data(points)
      .join('g')
      .attr('class', 'point')
      .attr('transform', d => `translate(${x(d.umap_x)},${y(d.umap_y)})`)
      .style('opacity', d =>
        selectedCluster === null ? 0.8 :
        d.cluster_id === selectedCluster ? 1 : 0.15
      )
      .style('cursor', 'pointer')

    nodes.each(function(d) {
      const node = d3.select(this)
      const shape = shapeForPassedBy(d.passed_by)
      const c = color(d.cluster_id)

      if (shape === 'triangle') {
        node.append('path')
          .attr('d', d3.symbol().type(d3.symbolTriangle).size(60)())
          .attr('fill', c)
          .attr('stroke', '#0f172a')
          .attr('stroke-width', 1)
      } else if (shape === 'star') {
        node.append('path')
          .attr('d', d3.symbol().type(d3.symbolStar).size(70)())
          .attr('fill', c)
          .attr('stroke', '#0f172a')
          .attr('stroke-width', 1)
      } else {
        node.append('circle')
          .attr('r', 4)
          .attr('fill', c)
          .attr('stroke', '#0f172a')
          .attr('stroke-width', 1)
      }
    })

    // Hover events
    nodes
      .on('mouseover', function(event, d) {
        d3.select(this).style('opacity', 1).raise()
        tooltip
          .style('opacity', 1)
          .html(`
            <strong>${d.title || 'Untitled'}</strong><br/>
            <span style="color:#94a3b8">Venue: ${d.venue || 'N/A'}</span><br/>
            <span style="color:#94a3b8">Filter: ${d.passed_by || 'N/A'}</span>
          `)
          .style('left', (event.pageX + 12) + 'px')
          .style('top', (event.pageY - 10) + 'px')
      })
      .on('mousemove', function(event) {
        tooltip
          .style('left', (event.pageX + 12) + 'px')
          .style('top', (event.pageY - 10) + 'px')
      })
      .on('mouseout', function(event, d) {
        d3.select(this).style('opacity',
          selectedCluster === null ? 0.8 :
          d.cluster_id === selectedCluster ? 1 : 0.15
        )
        tooltip.style('opacity', 0)
      })

    // Legend
    const legend = svg.append('g')
      .attr('transform', `translate(${width - 100}, 10)`)

    const legendItems = [
      { shape: 'circle', label: 'Top Venue' },
      { shape: 'triangle', label: 'High Velocity' },
      { shape: 'star', label: 'Manual' },
    ]

    legendItems.forEach((item, i) => {
      const lg = legend.append('g')
        .attr('transform', `translate(0, ${i * 18})`)

      if (item.shape === 'circle') {
        lg.append('circle').attr('r', 4).attr('cx', 4).attr('cy', 0).attr('fill', '#94a3b8')
      } else if (item.shape === 'triangle') {
        lg.append('path')
          .attr('d', d3.symbol().type(d3.symbolTriangle).size(50)())
          .attr('transform', 'translate(4,0)')
          .attr('fill', '#94a3b8')
      } else {
        lg.append('path')
          .attr('d', d3.symbol().type(d3.symbolStar).size(50)())
          .attr('transform', 'translate(4,0)')
          .attr('fill', '#94a3b8')
      }

      lg.append('text')
        .attr('x', 14)
        .attr('y', 4)
        .attr('fill', '#64748b')
        .attr('font-size', '10px')
        .text(item.label)
    })

    return () => {
      tooltip.remove()
    }
  }, [points, clusters, selectedCluster])

  return (
    <svg
      ref={svgRef}
      style={{ width: '100%', height: 'auto' }}
    />
  )
}
