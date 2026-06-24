import React from 'react'
import { CardProps, statusToColor, sizeToGridSpan } from './types'

const RiskCard: React.FC<CardProps> = ({ label, value, status, size }) => {
  const displayValue = value !== null && value !== undefined ? String(value) : '—'

  return (
    <div
      className="data-block"
      style={{ gridColumn: sizeToGridSpan(size) }}
    >
      <span className="data-block-key">{label}</span>
      <div
        className="data-block-health"
        style={{ borderLeftColor: statusToColor(status) }}
      >
        {displayValue}
      </div>
    </div>
  )
}

export default RiskCard
