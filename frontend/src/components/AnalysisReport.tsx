import React from 'react';

interface AnalysisReportProps {
  data: any;
}

const AnalysisReport: React.FC<AnalysisReportProps> = ({ data }) => {
  if (!data) return null;

  const verdictClass = (data.investment_verdict || 'neutral').toLowerCase();
  const hasAgentData = data.quantitative || data.qualitative || data.risk_governance;

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
            Confidence: <strong>{data.confidence_level || 'N/A'}</strong>
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
                {data.currency} {data.current_price?.toLocaleString() ?? 'N/A'}
              </div>
              <div className="currency-badge">{data.currency}</div>
            </div>
          )}
        </div>
      </div>

      {/* ═══ LIVE Analysis: Agent Cards ═══ */}
      {hasAgentData && (
        <div className="agent-sections">
          {/* Quantitative Agent */}
          {data.quantitative && (
            <div className="agent-card">
              <div className="agent-card-header">
                <div className="agent-card-icon quant">📊</div>
                <div>
                  <div className="agent-card-title">Quantitative Analysis</div>
                  <div className="agent-card-subtitle">The Accountant — Numbers & Ratios</div>
                </div>
              </div>
              <div className="agent-card-body">
                {data.quantitative.revenue_trend && (
                  <div className="agent-field">
                    <span className="agent-field-label">Revenue Trend</span>
                    <span className="agent-field-value">{data.quantitative.revenue_trend}</span>
                  </div>
                )}
                {data.quantitative.profit_margin_analysis && (
                  <div className="agent-field">
                    <span className="agent-field-label">Profit Margins</span>
                    <span className="agent-field-value">{data.quantitative.profit_margin_analysis}</span>
                  </div>
                )}
                {data.quantitative.valuation_assessment && (
                  <div className="agent-field">
                    <span className="agent-field-label">Valuation</span>
                    <span className="agent-field-value">{data.quantitative.valuation_assessment}</span>
                  </div>
                )}
                {data.quantitative.health_metrics && (
                  <div className="agent-field">
                    <span className="agent-field-label">Financial Health</span>
                    <span className="agent-field-value">{data.quantitative.health_metrics}</span>
                  </div>
                )}
                {data.quantitative.sector_specific && (
                  <div className="agent-field">
                    <span className="agent-field-label">Sector-Specific</span>
                    <span className="agent-field-value">{data.quantitative.sector_specific}</span>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Qualitative Agent */}
          {data.qualitative && (
            <div className="agent-card">
              <div className="agent-card-header">
                <div className="agent-card-icon qual">💡</div>
                <div>
                  <div className="agent-card-title">Qualitative Assessment</div>
                  <div className="agent-card-subtitle">The Strategist — Moat & Narrative</div>
                </div>
              </div>
              <div className="agent-card-body">
                {data.qualitative.moat_analysis && (
                  <div className="agent-field">
                    <span className="agent-field-label">Competitive Moat</span>
                    <span className="agent-field-value">{data.qualitative.moat_analysis}</span>
                  </div>
                )}
                {data.qualitative.management_quality && (
                  <div className="agent-field">
                    <span className="agent-field-label">Management Quality</span>
                    <span className="agent-field-value">{data.qualitative.management_quality}</span>
                  </div>
                )}
                {data.qualitative.growth_catalysts && (
                  <div className="agent-field">
                    <span className="agent-field-label">Growth Catalysts</span>
                    <span className="agent-field-value">{data.qualitative.growth_catalysts}</span>
                  </div>
                )}
                {data.qualitative.business_model && (
                  <div className="agent-field">
                    <span className="agent-field-label">Business Model</span>
                    <span className="agent-field-value">{data.qualitative.business_model}</span>
                  </div>
                )}
                {data.qualitative.narrative_explanation && (
                  <div className="agent-field">
                    <span className="agent-field-label">The "Why" Behind Numbers</span>
                    <span className="agent-field-value">{data.qualitative.narrative_explanation}</span>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Risk & Governance Agent */}
          {data.risk_governance && (
            <div className="agent-card">
              <div className="agent-card-header">
                <div className="agent-card-icon risk">🛡️</div>
                <div>
                  <div className="agent-card-title">Risk & Governance</div>
                  <div className="agent-card-subtitle">The Investigator — Red Flags & Skepticism</div>
                </div>
              </div>
              <div className="agent-card-body">
                {data.risk_governance.governance_score && (
                  <div className="agent-field">
                    <span className="agent-field-label">Governance</span>
                    <span className={`governance-badge ${data.risk_governance.governance_score}`}>
                      {data.risk_governance.governance_score?.toUpperCase()}
                    </span>
                  </div>
                )}
                {data.risk_governance.overall_risk_level && (
                  <div className="agent-field">
                    <span className="agent-field-label">Overall Risk Level</span>
                    <span className={`risk-badge ${data.risk_governance.overall_risk_level}`}>
                      {data.risk_governance.overall_risk_level?.toUpperCase()}
                    </span>
                  </div>
                )}
                {data.risk_governance.structural_risks && (
                  <div className="agent-field">
                    <span className="agent-field-label">Structural Risks</span>
                    <span className="agent-field-value">{data.risk_governance.structural_risks}</span>
                  </div>
                )}
                {data.risk_governance.insider_activity && (
                  <div className="agent-field">
                    <span className="agent-field-label">Insider Activity</span>
                    <span className="agent-field-value">{data.risk_governance.insider_activity}</span>
                  </div>
                )}
                {data.risk_governance.red_flags && data.risk_governance.red_flags.length > 0 && (
                  <div className="agent-field">
                    <span className="agent-field-label">Red Flags</span>
                    <ul className="red-flags-list">
                      {data.risk_governance.red_flags.map((flag: string, i: number) => (
                        <li key={i} className="red-flag-item">
                          <span className="red-flag-icon">⚠</span>
                          {flag}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      )}

      {/* ═══ Final Thesis (from live analysis) ═══ */}
      {data.final_thesis && (
        <div className="thesis-section">
          <h3>📝 Investment Thesis — Synthesizer Report</h3>
          <div className="thesis-content">{data.final_thesis}</div>
        </div>
      )}

      {/* ═══ Saved Report (markdown only, no live agent data) ═══ */}
      {!hasAgentData && data.report_markdown && (
        <div className="thesis-section">
          <h3>📝 Full Analysis Report</h3>
          <div className="thesis-content">{data.report_markdown}</div>
        </div>
      )}
    </div>
  );
};

export default AnalysisReport;
