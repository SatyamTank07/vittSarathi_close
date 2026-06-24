import React from 'react'
import { CardProps, statusToColor, sizeToGridSpan } from './types'

const MetricCard: React.FC<CardProps> = ({ label, value, status, size }) => {
  const displayValue = value !== null && value !== undefined ? String(value) : '—'

  return (
    <div
      className="data-block-nested-item"
      style={{ gridColumn: sizeToGridSpan(size) }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span className="nested-key">{label}</span>
        {status && (
          <span style={{
            width: '7px',
            height: '7px',
            borderRadius: '50%',
            background: statusToColor(status),
            display: 'inline-block',
            flexShrink: 0,
          }} />
        )}
      </div>
      <span
        className="nested-val"
        style={{ color: statusToColor(status) }}
      >
        {displayValue}
      </span>
    </div>
  )
}

export default MetricCard
