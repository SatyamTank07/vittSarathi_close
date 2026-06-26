import React from 'react';
import AgentCard from './AgentCard';
import DashboardGrid from './DashboardGrid';

interface AnalysisReportProps {
  data: any;
  highlightedCards: Set<string>;
}

const AnalysisReport: React.FC<AnalysisReportProps> = ({ data, highlightedCards }) => {
  if (!data) return null;

  const verdictRaw = (data.investment_verdict || 'neutral').toLowerCase();
  const verdictClass = verdictRaw.includes('bullish')
    ? 'bullish'
    : verdictRaw.includes('bearish')
    ? 'bearish'
    : 'neutral';

  return (
    <div className="report-view animate-fade-in">
      {/* ═══ Verdict Banner ═══ */}
      <div className={`verdict-banner ${verdictClass}`}>
        <div className="verdict-left">
          <span className="verdict-label">Investment Verdict</span>
          <span className={`verdict-value ${verdictClass}`}>
            {data.investment_verdict || 'N/A'}
          </span>
        </div>
        <div className="verdict-right">
          <span className="verdict-confidence">
            Confidence: <strong>{data.confidence_level ? `${(parseFloat(data.confidence_level) * 100).toFixed(0)}%` : 'N/A'}</strong>
          </span>
          {data.analysis_duration_seconds && (
            <span className="verdict-duration">
              Analysis completed in {data.analysis_duration_seconds}s
            </span>
          )}
        </div>
      </div>

      {/* ═══ Company Hero ═══ */}
      <div className="company-hero-card">
        <div className="hero-top">
          <div className="hero-meta">
            <div className="symbol-pill">{data.ticker}</div>
            <h2 className="company-name">{data.company_name}</h2>
            <div className="sector-info">
              <span className="sector-tag">{data.sector}</span>
              <span className="industry-tag">{data.industry}</span>
            </div>
          </div>
          {data.current_price && (
            <div className="price-container">
              <div className="price-label">Current Price</div>
              <div className="price-value">
                {data.currency} {data.current_price?.toLocaleString('en-IN')}
              </div>
              <div className="currency-badge">{data.currency}</div>
            </div>
          )}
        </div>
      </div>

      {/* ═══ Dynamic Dashboard Grid ═══ */}
      {data.ui_manifest ? (
        <DashboardGrid
          uiManifest={data.ui_manifest}
          dashboardData={data}
          highlightedCards={highlightedCards}
        />
      ) : (
        // fallback — old hardcoded cards when no manifest present (dev/dummy data)
        <div className="agent-cards-grid">
          {/* Quantitative Agent */}
          {data.quantitative && (
            <AgentCard
              id="card-quant"
              icon="📊"
              title="Quantitative Analysis"
              subtitle={`The Accountant — ${data.quantitative.industry_framework_used || 'Financial Metrics'}`}
              status={data.agent_statuses?.quantitative === 'completed' ? 'completed' : 'idle'}
              isHighlighted={highlightedCards.has('card-quant')}
              accentClass="quant"
              data={{
                ...data.quantitative.analysis_blocks,
                ...(data.quantitative.raw_ratios && { 'Key Ratios': data.quantitative.raw_ratios }),
                ...(data.quantitative.overall_quantitative_health && { overall_quantitative_health: data.quantitative.overall_quantitative_health }),
              }}
            />
          )}

          {/* Qualitative Agent */}
          {data.qualitative && (
            <AgentCard
              id="card-qual"
              icon="💡"
              title="Qualitative Assessment"
              subtitle="The Strategist — Moat & Narrative"
              status={data.agent_statuses?.qualitative === 'completed' ? 'completed' : 'idle'}
              isHighlighted={highlightedCards.has('card-qual')}
              accentClass="qual"
              data={{
                'Competitive Moat': data.qualitative.moat_analysis,
                'Management Quality': data.qualitative.management_quality,
                'Growth Catalysts': data.qualitative.growth_catalysts,
                'Business Model': data.qualitative.business_model,
                'The "Why" Behind Numbers': data.qualitative.narrative_explanation,
              }}
            />
          )}

          {/* Risk & Governance Agent */}
          {data.risk_governance && (
            <AgentCard
              id="card-risk"
              icon="🛡️"
              title="Risk & Governance"
              subtitle={`The Investigator — ${data.risk_governance.industry_framework_used || 'Risk Assessment'}`}
              status={data.agent_statuses?.risk_governance === 'completed' ? 'completed' : 'idle'}
              isHighlighted={highlightedCards.has('card-risk')}
              accentClass="risk"
              data={{
                ...data.risk_governance.analysis_blocks,
                ...(data.risk_governance.raw_metrics && { 'Governance Metrics': data.risk_governance.raw_metrics }),
                ...(data.risk_governance.overall_governance_health && { overall_governance_health: data.risk_governance.overall_governance_health }),
              }}
            />
          )}

          {/* Synthesizer Agent */}
          <AgentCard
            id="card-synth"
            icon="📝"
            title="Synthesizer — CIO Report"
            subtitle="Chief Investment Officer — Final Verdict"
            status={data.agent_statuses?.synthesizer === 'completed' ? 'completed' : 'idle'}
            isHighlighted={highlightedCards.has('card-synth')}
            accentClass="synth"
            data={{
              'Investment Rating': data.investment_verdict || 'N/A',
              'Conviction Score': data.confidence_level ? `${(parseFloat(data.confidence_level) * 100).toFixed(0)}%` : 'N/A',
              'Analysis Duration': data.analysis_duration_seconds ? `${data.analysis_duration_seconds}s` : 'N/A',
            }}
          />
        </div>
      )}

      {/* ═══ Final Thesis ═══ */}
      {data.final_thesis && (
        <div className="thesis-section">
          <h3>📝 Investment Thesis — Full Report</h3>
          <div className="thesis-content">{data.final_thesis}</div>
        </div>
      )}
    </div>
  );
};

export default AnalysisReport;
