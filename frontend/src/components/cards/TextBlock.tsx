import React, { useState } from 'react'
import { CardProps, sizeToGridSpan } from './types'

const TextBlock: React.FC<CardProps> = ({ label, value, status, size }) => {
  const [expanded, setExpanded] = useState(false)
  const displayValue = value !== null && value !== undefined ? String(value) : '—'

  return (
    <div
      className="data-block"
      style={{ gridColumn: sizeToGridSpan(size) }}
    >
      <span className="data-block-key">{label}</span>
      <span
        className={`data-block-value ${expanded ? 'expanded' : 'truncated'}`}
        onClick={() => setExpanded(prev => !prev)}
        style={{ cursor: 'pointer' }}
        title={expanded ? 'Click to collapse' : 'Click to expand'}
      >
        {displayValue}
      </span>
    </div>
  )
}

export default TextBlock
