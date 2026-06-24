import React from 'react';
import MetricCard    from './cards/MetricCard';
import PillarCard    from './cards/PillarCard';
import RiskCard      from './cards/RiskCard';
import TextBlock     from './cards/TextBlock';
import SentimentBlock from './cards/SentimentBlock';

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

function renderComponent(component: UIComponent, dashboardData: any) {
  const value = getByPath(dashboardData, component.data_path);
  const sharedProps = {
    label: component.label,
    value,
    status: component.status as any,
    size: component.size as any,
  };

  switch (component.component_type) {
    case 'metric_card':     return <MetricCard     key={component.id} {...sharedProps} />;
    case 'pillar_card':     return <PillarCard     key={component.id} {...sharedProps} />;
    case 'risk_card':       return <RiskCard       key={component.id} {...sharedProps} />;
    case 'text_block':      return <TextBlock      key={component.id} {...sharedProps} />;
    case 'sentiment_block': return <SentimentBlock key={component.id} {...sharedProps} />;
    case 'macro_block':     return <TextBlock      key={component.id} {...sharedProps} />;
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
