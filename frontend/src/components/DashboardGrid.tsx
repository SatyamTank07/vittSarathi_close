import React, { useState } from 'react';

// Interfaces matching backend models
export interface UIComponent {
  id: string;
  component_type: string;
  label: string;
  data_path: string;
  order: number;
  size: 'small' | 'medium' | 'large' | 'full';
  status: string | null;
}

export interface UIManifest {
  layout_sections: Record<string, UIComponent[]>;
}

function getByPath(obj: any, path: string): any {
  if (!obj || !path) return null;
  return path.split('.').reduce((cursor, key) => {
    if (cursor === null || cursor === undefined) return null;
    return cursor[key];
  }, obj);
}

function statusToColor(status: string | null): string {
  if (status === 'green')  return 'var(--success)';
  if (status === 'yellow') return 'var(--warning)';
  if (status === 'red')    return 'var(--danger)';
  return 'var(--text-dim)';
}

function statusToClass(status: string | null): string {
  if (status === 'green')  return 'completed';
  if (status === 'yellow') return 'running';
  if (status === 'red')    return 'error';
  return 'idle';
}

function renderMetricCard(component: UIComponent, value: any) {
  return (
    <div
      key={component.id}
      className="data-block-nested-item"
      style={{ gridColumn: component.size === 'medium' ? 'span 2' : 'span 1' }}
    >
      <span className="nested-key">{component.label}</span>
      <span className="nested-val" style={{ color: statusToColor(component.status) }}>
        {value !== null && value !== undefined ? String(value) : '—'}
      </span>
    </div>
  );
}

function renderPillarCard(component: UIComponent, value: any) {
  if (!value) return null;
  return (
    <div key={component.id} className="data-block">
      <span className="data-block-key">{component.label}</span>
      <span className="data-block-value">{value.thesis || value}</span>
      {value.supporting_metrics?.length > 0 && (
        <div className="data-block-nested">
          {value.supporting_metrics.map((m: any, i: number) => (
            <div key={i} className="data-block-nested-item">
              <span className="nested-key">{m.metric}</span>
              <span
                className="nested-val"
                style={{ color: statusToColor(m.status?.toLowerCase() || null) }}
              >
                {m.value}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function renderRiskCard(component: UIComponent, value: any) {
  return (
    <div key={component.id} className="data-block">
      <span className="data-block-key">{component.label}</span>
      <div
        className="data-block-health"
        style={{ borderLeftColor: statusToColor(component.status) }}
      >
        {value !== null && value !== undefined ? String(value) : '—'}
      </div>
    </div>
  );
}

const TextBlock: React.FC<{ component: UIComponent; value: any }> = ({ component, value }) => {
  const [expanded, setExpanded] = useState(false);
  return (
    <div key={component.id} className="data-block">
      <span className="data-block-key">{component.label}</span>
      <span
        className={`data-block-value ${expanded ? 'expanded' : 'truncated'}`}
        onClick={() => setExpanded(e => !e)}
      >
        {value !== null && value !== undefined ? String(value) : '—'}
      </span>
    </div>
  );
};

function renderSentimentBlock(component: UIComponent, value: any) {
  if (!value) return null;
  return (
    <div key={component.id} className="data-block">
      <span className="data-block-key">{component.label}</span>
      {value.overall_mood && (
        <span className="symbol-pill" style={{ display: 'inline-block', marginBottom: '0.5rem' }}>
          {value.overall_mood}
        </span>
      )}
      {value.dominant_news_themes?.length > 0 && (
        <div className="sector-info" style={{ flexWrap: 'wrap', gap: '0.4rem' }}>
          {value.dominant_news_themes.map((theme: string, i: number) => (
            <span key={i} className="sector-tag">{theme}</span>
          ))}
        </div>
      )}
    </div>
  );
}

function renderComponent(component: UIComponent, dashboardData: any) {
  const value = getByPath(dashboardData, component.data_path);

  switch (component.component_type) {
    case 'metric_card':     return renderMetricCard(component, value);
    case 'pillar_card':     return renderPillarCard(component, value);
    case 'risk_card':       return renderRiskCard(component, value);
    case 'text_block':      return <TextBlock key={component.id} component={component} value={value} />;
    case 'sentiment_block': return renderSentimentBlock(component, value);
    case 'macro_block':     return <TextBlock key={component.id} component={component} value={value} />;
    default:                return null;
  }
}

interface DashboardGridProps {
  uiManifest: UIManifest | null;
  dashboardData: any;
}

const DashboardGrid: React.FC<DashboardGridProps> = ({ uiManifest, dashboardData }) => {
  if (!uiManifest || !dashboardData) return null;

  const sectionIcons: Record<string, string> = {
    key_ratios:         '📊',
    investment_pillars: '💡',
    risk_dashboard:     '🛡️',
    sentiment:          '📡',
    executive_summary:  '📝',
  };

  return (
    <div className="agent-cards-grid">
      {Object.entries(uiManifest.layout_sections).map(([sectionName, components]) => {
        if (!components || components.length === 0) return null;

        // sort by order field
        const sorted = [...components].sort((a, b) => a.order - b.order);

        return (
          <div
            key={sectionName}
            className="agent-card-dynamic"
            style={{
              // full-width sections span both grid columns
              gridColumn: sorted.some(c => c.size === 'full') ? '1 / -1' : 'span 1'
            }}
          >
            {/* Section header — reuses existing agent card header CSS */}
            <div className="agent-card-header-section">
              <div className="agent-card-icon-wrap quant">
                {sectionIcons[sectionName] || '📋'}
              </div>
              <div className="agent-card-header-text">
                <span className="agent-card-title-text">
                  {sectionName.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}
                </span>
              </div>
            </div>

            {/* Section content */}
            <div className="agent-card-content">
              {/* Metric cards get a nested grid layout */}
              {sectionName === 'key_ratios' ? (
                <div className="data-block-nested">
                  {sorted.map(c => renderComponent(c, dashboardData))}
                </div>
              ) : (
                sorted.map(c => renderComponent(c, dashboardData))
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

export default DashboardGrid;
