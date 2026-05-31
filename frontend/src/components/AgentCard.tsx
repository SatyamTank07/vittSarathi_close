import React, { useState } from 'react';

interface AgentCardProps {
  id: string;
  icon: string;
  title: string;
  subtitle: string;
  status: 'idle' | 'running' | 'completed' | 'error';
  isHighlighted: boolean;
  data: Record<string, any> | null;
  accentClass?: string; // 'quant' | 'qual' | 'risk' | 'synth' | 'orch'
}

const AgentCard: React.FC<AgentCardProps> = ({
  id,
  icon,
  title,
  subtitle,
  status,
  isHighlighted,
  data,
  accentClass = 'quant',
}) => {
  const [expandedKeys, setExpandedKeys] = useState<Set<string>>(new Set());

  const toggleExpand = (key: string) => {
    setExpandedKeys((prev) => {
      const next = new Set(prev);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  };

  const formatKey = (key: string): string => {
    return key
      .replace(/_/g, ' ')
      .replace(/([A-Z])/g, ' $1')
      .replace(/^./, (s) => s.toUpperCase())
      .trim();
  };

  const formatNumber = (val: number): string => {
    if (Math.abs(val) >= 1e9) return `${(val / 1e9).toFixed(2)}B`;
    if (Math.abs(val) >= 1e6) return `${(val / 1e6).toFixed(2)}M`;
    if (Math.abs(val) >= 1e3) return `${(val / 1e3).toFixed(1)}K`;
    if (Number.isInteger(val)) return val.toLocaleString();
    return val.toFixed(2);
  };

  const renderValue = (key: string, value: any): React.ReactNode => {
    if (value === null || value === undefined) {
      return <span className="data-block-value" style={{ color: 'var(--text-dim)' }}>N/A</span>;
    }

    // String
    if (typeof value === 'string') {
      const isLong = value.length > 200;
      const isExpanded = expandedKeys.has(key);
      return (
        <span
          className={`data-block-value ${isLong && !isExpanded ? 'truncated' : ''} ${isExpanded ? 'expanded' : ''}`}
          onClick={isLong ? () => toggleExpand(key) : undefined}
          style={isLong ? { cursor: 'pointer' } : undefined}
        >
          {value}
          {isLong && !isExpanded && (
            <span style={{ color: 'var(--primary)', fontSize: '0.78rem', marginLeft: '0.25rem' }}>▸ Read more</span>
          )}
        </span>
      );
    }

    // Number
    if (typeof value === 'number') {
      return <span className="data-block-value" style={{ fontWeight: 600, color: 'var(--secondary)', fontFamily: 'var(--font-heading)' }}>{formatNumber(value)}</span>;
    }

    // Boolean
    if (typeof value === 'boolean') {
      return (
        <span className="data-block-value" style={{ color: value ? 'var(--primary)' : 'var(--danger)' }}>
          {value ? '✓ Yes' : '✗ No'}
        </span>
      );
    }

    // Array of strings
    if (Array.isArray(value) && value.length > 0 && typeof value[0] === 'string') {
      return (
        <ul className="data-block-list">
          {value.map((item, i) => (
            <li key={i}>{item}</li>
          ))}
        </ul>
      );
    }

    // Array of objects (e.g., supporting_metrics)
    if (Array.isArray(value) && value.length > 0 && typeof value[0] === 'object') {
      return (
        <div className="data-block-nested">
          {value.map((item, i) => {
            const entries = Object.entries(item);
            return entries.map(([k, v]) => (
              <div key={`${i}-${k}`} className="data-block-nested-item">
                <span className="nested-key">{formatKey(k)}</span>
                <span className="nested-val">{String(v)}</span>
              </div>
            ));
          })}
        </div>
      );
    }

    // Nested object (e.g., raw_ratios, raw_metrics)
    if (typeof value === 'object' && !Array.isArray(value)) {
      const entries = Object.entries(value);
      return (
        <div className="data-block-nested">
          {entries.map(([k, v]) => (
            <div key={k} className="data-block-nested-item">
              <span className="nested-key">{formatKey(k)}</span>
              <span className="nested-val">{typeof v === 'number' ? formatNumber(v) : String(v)}</span>
            </div>
          ))}
        </div>
      );
    }

    return <span className="data-block-value">{String(value)}</span>;
  };

  return (
    <div
      id={id}
      className={`agent-card-dynamic ${isHighlighted ? 'highlighted' : ''}`}
    >
      {/* Header */}
      <div className="agent-card-header-section">
        <div className={`agent-card-icon-wrap ${accentClass}`}>
          {icon}
        </div>
        <div className="agent-card-header-text">
          <div className="agent-card-title-text">{title}</div>
          <div className="agent-card-subtitle-text">{subtitle}</div>
        </div>
        <div className={`agent-card-status ${status}`} title={status} />
      </div>

      {/* Content */}
      <div className="agent-card-content">
        {data && Object.entries(data).map(([key, value]) => {
          // Special rendering for 'overall_*' or '*_health' keys — show as highlighted summary
          const isHealthSummary = key.startsWith('overall_') || key.endsWith('_health');
          
          if (isHealthSummary && typeof value === 'string') {
            return (
              <div key={key} className="data-block">
                <span className="data-block-key">{formatKey(key)}</span>
                <div className="data-block-health">{value}</div>
              </div>
            );
          }

          return (
            <div key={key} className="data-block">
              <span className="data-block-key">{formatKey(key)}</span>
              {renderValue(key, value)}
            </div>
          );
        })}
        {!data && (
          <div style={{ color: 'var(--text-dim)', fontStyle: 'italic', fontSize: '0.88rem' }}>
            Awaiting agent response...
          </div>
        )}
      </div>
    </div>
  );
};

export default AgentCard;
