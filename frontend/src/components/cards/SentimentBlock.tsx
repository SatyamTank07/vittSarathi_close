import React from 'react'
import { CardProps, sizeToGridSpan } from './types'

const SentimentBlock: React.FC<CardProps> = ({ label, value, status, size }) => {
  // graceful fallback if value is not the expected object
  if (!value || typeof value !== 'object') {
    return (
      <div className="data-block" style={{ gridColumn: sizeToGridSpan(size) }}>
        <span className="data-block-key">{label}</span>
        <span className="data-block-value">{String(value ?? '—')}</span>
      </div>
    )
  }

  const mood = value.overall_mood || null
  const breakdown = value.finbert_score_breakdown || {}
  const themes = value.dominant_news_themes || []

  // mood → colour
  const moodColor = mood?.toLowerCase().includes('positive') ? 'var(--success)'
    : mood?.toLowerCase().includes('negative') ? 'var(--danger)'
    : 'var(--warning)'

  return (
    <div
      className="data-block"
      style={{ gridColumn: sizeToGridSpan(size) }}
    >
      <span className="data-block-key">{label}</span>

      {/* Mood badge */}
      {mood && (
        <span
          className="symbol-pill"
          style={{
            display: 'inline-block',
            marginBottom: '0.5rem',
            background: `${moodColor}18`,
            borderColor: `${moodColor}30`,
            color: moodColor,
          }}
        >
          {mood}
        </span>
      )}

      {/* Score breakdown */}
      {Object.keys(breakdown).length > 0 && (
        <div className="data-block-nested" style={{ marginBottom: '0.5rem' }}>
          {Object.entries(breakdown).map(([key, val]) => (
            <div key={key} className="data-block-nested-item">
              <span className="nested-key">{key}</span>
              <span className="nested-val">{String(val)}%</span>
            </div>
          ))}
        </div>
      )}

      {/* News themes */}
      {themes.length > 0 && (
        <div className="sector-info" style={{ flexWrap: 'wrap', gap: '0.4rem', marginTop: '0.25rem' }}>
          {themes.map((theme: string, i: number) => (
            <span key={i} className="sector-tag">{theme}</span>
          ))}
        </div>
      )}
    </div>
  )
}

export default SentimentBlock
