import React, { useEffect, useRef } from 'react'
import * as d3 from 'd3'

const shapeForPassedBy = (passedBy) => {
  if (!passedBy) return 'circle'
  if (passedBy.includes('manual')) return 'star'
  if (passedBy.includes('velocity')) return 'triangle'
  return 'circle'
}

export default function ClusterMap({ points, clusters, selectedCluster, onSelectCluster }) {
  const svgRef = useRef(null)
  const tooltipRef = useRef(null)

  useEffect(() => {
    if (!points || points.length === 0) return

    const svg = d3.select(svgRef.current)
    svg.selectAll('*').remove()

    const width = 700
    const height = 500
    const margin = { top: 20, right: 20, bottom: 20, left: 20 }
    const innerW = width - margin.left - margin.right
    const innerH = height - margin.top - margin.bottom

    const g = svg
      .attr('viewBox', `0 0 ${width} ${height}`)
      .append('g')
      .attr('transform', `translate(${margin.left},${margin.top})`)

    // Scales
    const xPad = 0.1
    const xExtent = d3.extent(points, d => d.umap_x)
    const yExtent = d3.extent(points, d => d.umap_y)
    const xRange = xExtent[1] - xExtent[0] || 1
    const yRange = yExtent[1] - yExtent[0] || 1
    const x = d3.scaleLinear().domain([xExtent[0] - xRange * xPad, xExtent[1] + xRange * xPad]).range([0, innerW])
    const y = d3.scaleLinear().domain([yExtent[0] - yRange * xPad, yExtent[1] + yRange * xPad]).range([innerH, 0])

    // Color scale
    const clusterIds = [...new Set(points.map(d => d.cluster_id))].sort((a, b) => a - b)
    const color = d3.scaleOrdinal(d3.schemeTableau10).domain(clusterIds)

    // Cluster name map
    const clusterNameMap = {}
    if (clusters) {
      clusters.forEach(c => { clusterNameMap[c.id] = c.name })
    }

    // Compute cluster centroids
    const centroids = {}
    clusterIds.forEach(cid => {
      const cPoints = points.filter(p => p.cluster_id === cid)
      if (cPoints.length > 0) {
        centroids[cid] = {
          x: d3.mean(cPoints, p => p.umap_x),
          y: d3.mean(cPoints, p => p.umap_y),
          count: cPoints.length,
        }
      }
    })

    // Draw convex hulls for each cluster (background)
    clusterIds.forEach(cid => {
      const cPoints = points.filter(p => p.cluster_id === cid)
      if (cPoints.length >= 3) {
        const hullPoints = cPoints.map(p => [x(p.umap_x), y(p.umap_y)])
        const hull = d3.polygonHull(hullPoints)
        if (hull) {
          g.append('path')
            .attr('d', `M${hull.join('L')}Z`)
            .attr('fill', color(cid))
            .attr('fill-opacity', selectedCluster === null ? 0.06 : (selectedCluster === cid ? 0.12 : 0.02))
            .attr('stroke', color(cid))
            .attr('stroke-opacity', selectedCluster === null ? 0.2 : (selectedCluster === cid ? 0.4 : 0.05))
            .attr('stroke-width', 1)
            .style('cursor', 'pointer')
            .on('click', () => {
              if (onSelectCluster) onSelectCluster(selectedCluster === cid ? null : cid)
            })
        }
      }
    })

    // Tooltip
    if (!tooltipRef.current) {
      tooltipRef.current = d3.select('body').append('div')
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
        .style('max-width', '300px')
    }
    const tooltip = tooltipRef.current

    // Draw points
    const nodes = g.selectAll('.point')
      .data(points)
      .join('g')
      .attr('class', 'point')
      .attr('transform', d => `translate(${x(d.umap_x)},${y(d.umap_y)})`)
      .style('opacity', d =>
        selectedCluster === null ? 0.85 :
        d.cluster_id === selectedCluster ? 1 : 0.1
      )
      .style('cursor', 'pointer')

    nodes.each(function(d) {
      const node = d3.select(this)
      const shape = shapeForPassedBy(d.passed_by)
      const c = color(d.cluster_id)

      if (shape === 'triangle') {
        node.append('path')
          .attr('d', d3.symbol().type(d3.symbolTriangle).size(80)())
          .attr('fill', c)
          .attr('stroke', '#0f172a')
          .attr('stroke-width', 1)
      } else if (shape === 'star') {
        node.append('path')
          .attr('d', d3.symbol().type(d3.symbolStar).size(90)())
          .attr('fill', c)
          .attr('stroke', '#0f172a')
          .attr('stroke-width', 1)
      } else {
        node.append('circle')
          .attr('r', 5)
          .attr('fill', c)
          .attr('stroke', '#0f172a')
          .attr('stroke-width', 1)
      }
    })

    // Hover
    nodes
      .on('mouseover', function(event, d) {
        d3.select(this).style('opacity', 1).raise()
        const cName = clusterNameMap[d.cluster_id] || `Cluster ${d.cluster_id}`
        tooltip
          .style('opacity', 1)
          .html(`
            <div style="font-weight:600;margin-bottom:4px">${d.title || 'Untitled'}</div>
            <div style="color:#60a5fa;font-size:11px;margin-bottom:2px">${cName}</div>
            <div style="color:#94a3b8;font-size:11px">
              ${d.venue ? `Venue: ${d.venue}` : ''}
              ${d.passed_by ? ` | ${d.passed_by}` : ''}
            </div>
          `)
          .style('left', (event.pageX + 14) + 'px')
          .style('top', (event.pageY - 14) + 'px')
      })
      .on('mousemove', function(event) {
        tooltip
          .style('left', (event.pageX + 14) + 'px')
          .style('top', (event.pageY - 14) + 'px')
      })
      .on('mouseout', function(event, d) {
        d3.select(this).style('opacity',
          selectedCluster === null ? 0.85 :
          d.cluster_id === selectedCluster ? 1 : 0.1
        )
        tooltip.style('opacity', 0)
      })

    // Draw cluster name labels at centroids
    clusterIds.forEach(cid => {
      const cent = centroids[cid]
      if (!cent) return
      const name = clusterNameMap[cid] || `Cluster ${cid}`
      // Truncate long names
      const shortName = name.length > 25 ? name.slice(0, 22) + '...' : name

      const labelG = g.append('g')
        .attr('transform', `translate(${x(cent.x)},${y(cent.y)})`)
        .style('pointer-events', 'none')
        .style('opacity', selectedCluster === null ? 0.9 : (selectedCluster === cid ? 1 : 0.15))

      // Background rect
      labelG.append('rect')
        .attr('x', -4)
        .attr('y', -14)
        .attr('width', shortName.length * 5.5 + 16)
        .attr('height', 18)
        .attr('rx', 3)
        .attr('fill', '#0f172a')
        .attr('fill-opacity', 0.85)
        .attr('stroke', color(cid))
        .attr('stroke-opacity', 0.5)

      labelG.append('text')
        .attr('x', 4)
        .attr('y', 0)
        .attr('fill', color(cid))
        .attr('font-size', '11px')
        .attr('font-weight', 600)
        .text(`${shortName} (${cent.count})`)
    })

    return () => {
      if (tooltipRef.current) {
        tooltipRef.current.style('opacity', 0)
      }
    }
  }, [points, clusters, selectedCluster, onSelectCluster])

  // Cleanup tooltip on unmount
  useEffect(() => {
    return () => {
      if (tooltipRef.current) {
        tooltipRef.current.remove()
        tooltipRef.current = null
      }
    }
  }, [])

  return (
    <svg
      ref={svgRef}
      style={{ width: '100%', height: 'auto' }}
    />
  )
}
