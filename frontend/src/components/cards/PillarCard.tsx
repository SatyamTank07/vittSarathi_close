import React from 'react'
import { CardProps, statusToColor, sizeToGridSpan } from './types'

const PillarCard: React.FC<CardProps> = ({ label, value, status, size }) => {
  // value can be an InvestmentPillar object or a plain string
  const thesis = typeof value === 'object' && value !== null
    ? (value.thesis || JSON.stringify(value))
    : String(value ?? '—')

  const metrics = typeof value === 'object' && value !== null
    ? (value.supporting_metrics || [])
    : []

  return (
    <div
      className="data-block"
      style={{ gridColumn: sizeToGridSpan(size) }}
    >
      <span className="data-block-key">{label}</span>
      <span className="data-block-value">{thesis}</span>

      {metrics.length > 0 && (
        <div className="data-block-nested" style={{ marginTop: '0.5rem' }}>
          {metrics.map((m: any, i: number) => {
            const metricStatus = m.status?.toLowerCase() === 'green' ? 'green'
              : m.status?.toLowerCase() === 'yellow' ? 'yellow'
              : m.status?.toLowerCase() === 'red' ? 'red'
              : null
            return (
              <div key={i} className="data-block-nested-item">
                <span className="nested-key">{m.metric}</span>
                <span
                  className="nested-val"
                  style={{ color: statusToColor(metricStatus) }}
                >
                  {m.value}
                </span>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

export default PillarCard
