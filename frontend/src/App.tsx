import { useState } from 'react';
import './App.css';
import Header from './components/Header';
import AnalysisReport from './components/AnalysisReport';
import ChatPanel from './components/ChatPanel';
// @ts-ignore
import { useAnalysis } from './hooks/useAnalysis';
// ═══ Dummy Data — matches backend SharedState schema ═══
const dummyAnalysisData = {
  ticker: "TCS.NS",
  company_name: "Tata Consultancy Services Limited",
  sector: "Technology",
  industry: "Information Technology Services",
  currency: "INR",
  current_price: 4125.50,
  investment_verdict: "Moderately Bullish",
  confidence_level: "0.78",
  analysis_duration_seconds: 34.2,

  quantitative: {
    industry_framework_used: "IT Services & Consulting",
    analysis_blocks: {
      "Revenue Growth Trajectory": "TCS reported ₹2,40,893 Cr revenue in FY24, representing 8.1% YoY growth. The 5-year CAGR stands at 12.3%, driven by digital transformation deals in BFSI and retail verticals. Q4 FY24 showed sequential improvement with $7.7B in new deal wins.",
      "Margin Architecture": "Operating margins have stabilized at 24.2% (EBIT). EBITDA margins at 27.1% reflect disciplined cost management. Attrition decline from 21.3% to 12.8% has significantly reduced recruitment costs and improved project delivery efficiency.",
      "Valuation Assessment": "Trading at 31.2x trailing P/E vs. 5-year median of 29.5x. Forward P/E of 27.8x prices in moderate growth expectations. PEG ratio of 2.1 suggests slight premium to growth-adjusted fair value. EV/EBITDA at 22.4x is reasonable for a mega-cap IT compounder.",
      "Cash Flow Quality": "Free Cash Flow of ₹38,200 Cr represents an FCF/Net Income conversion of 95.2% — elite level. Operating Cash Flow margin of 21.8% supports consistent buybacks and a 43% dividend payout ratio.",
      "Return on Capital": "ROE of 47.2% and ROCE of 58.1% are best-in-class among global IT services peers. The asset-light model and negative working capital cycle create a structural advantage in capital efficiency."
    },
    raw_ratios: {
      pe_ratio: 31.2,
      pb_ratio: 14.8,
      roe: 47.2,
      roce: 58.1,
      debt_to_equity: 0.08,
      current_ratio: 2.31
    },
    overall_quantitative_health: "Strong — TCS demonstrates best-in-class capital efficiency with elite FCF conversion. Valuations are at a slight premium but justified by consistent execution and sector-leading margins."
  },

  qualitative: {
    moat_analysis: "Wide moat through scale advantages (600K+ employees), deep client relationships (top 10 clients contribute 35% revenue with avg. tenure >15 years), and domain expertise across 6 industry verticals. The TCS BaNCS platform in BFSI creates high switching costs.",
    management_quality: "Stellar. K Krithivasan (CEO since Jun 2023) has maintained the TCS playbook of steady-state execution. Board governance scores: 9.2/10 (CRISIL). Seamless CEO transitions demonstrate institutional maturity.",
    growth_catalysts: "1) Generative AI services ramp-up (2,500+ engagements in FY24). 2) Cloud transformation deals from large enterprises still in early innings. 3) Market share gains from distressed competitors. 4) Japan and Middle East market expansion.",
    business_model: "Asset-light IT services model with 95%+ recurring revenue. Revenue mix: 37% BFSI, 15% Retail, 14% Manufacturing, 12% Telecom, 22% Others. High operating leverage — each 1% revenue growth adds ~40bps to margins.",
    narrative_explanation: "TCS is the 'steady compounder' of Indian IT — it doesn't chase hyper-growth but delivers consistent 8-12% revenue growth with 24-26% margins like clockwork. In uncertain macro, clients consolidate spend with trusted large-scale vendors, and TCS is the #1 beneficiary."
  },

  risk_governance: {
    industry_framework_used: "IT Services",
    analysis_blocks: {
      "Client Concentration Risk": "Top 10 clients account for 35% of revenue, with no single client exceeding 7%. This is within acceptable bounds for large IT services firms. However, any loss of a top-5 client could impact 2-3% of revenue.",
      "Currency & Macro Risk": "52% revenue in USD exposes TCS to INR appreciation risk. Each 1% INR appreciation vs. USD impacts margins by ~40bps. Cross-currency hedging covers ~60% of next 12-month receivables.",
      "Talent & Attrition Risk": "Attrition at 12.8% (LTM) is near historic lows. However, GenAI skill concentration risk is emerging — top 15% of AI-skilled employees are being aggressively targeted by hyperscalers.",
      "Technology Disruption": "GenAI poses a dual risk/opportunity. While TCS has embraced it (2,500+ engagements), there's a structural risk that AI-driven automation could reduce headcount-based billing over the long term."
    },
    raw_metrics: {
      promoter_holding: 72.3,
      promoter_pledging: 0,
      institutional_holding: 18.7,
      board_independence_pct: 66.7
    },
    overall_governance_health: "Excellent — Zero promoter pledging, 66.7% board independence, clean auditor reports for 20+ consecutive years. Tata group parentage provides structural governance guardrails."
  },

  final_thesis: "## Executive Summary\nTCS represents a high-quality compounder in the Indian IT services space with best-in-class capital efficiency (47.2% ROE, 95.2% FCF conversion). The company trades at a slight premium (31.2x P/E) to its historical median, justified by consistent execution and sector-leading margins.\n\n## Investment Pillars\n### Capital Efficiency Engine\n**Thesis**: TCS's asset-light model generates best-in-class returns with minimal capital requirements.\n- ROE: 47.2% (vs. industry median 22%)\n- ROCE: 58.1%\n- FCF Conversion: 95.2%\n\n### Digital Transformation Tailwind\n**Thesis**: Enterprise cloud and AI adoption creates a multi-year revenue runway.\n- 2,500+ GenAI engagements started in FY24\n- $7.7B in new deal wins in Q4 FY24\n\n## Key Risk Dashboard\n- **Currency Risk**: Medium — 52% USD exposure with partial hedging\n- **AI Disruption**: Low-Medium — Early mover advantage but business model transition needed\n- **Client Concentration**: Low — Well diversified across 1000+ active clients\n- **Valuation Risk**: Low-Medium — Slight premium to historical median",

  agent_statuses: {
    orchestrator: "completed",
    quantitative: "completed",
    qualitative: "completed",
    risk_governance: "completed",
    synthesizer: "completed"
  }
};

function App() {
  const {
    dashboardData,
    chatHistory,
    loading,
    error,
    agentStatuses,
    clarificationNeeded,
    clarificationCandidates,
    clarificationMessage,
    submitQuery,
    resolveClarification,
    sessionId,
    highlightedCards,
  } = useAnalysis();

  return (
    <div className="app-container">
      <Header />

      <main className="app-main-content">
        {/* Loading State */}
        {loading && (
          <div className="analysis-loading animate-fade-in">
            <div className="analysis-spinner" />
            <h2>Analyzing...</h2>
            <p>AI agents are working...</p>
            <div className="agent-progress">
              {Object.entries(agentStatuses || {}).map(([agent, status]) => {
                const getIcon = (name: string) => {
                  if (name.includes('orchestrator')) return '🎯';
                  if (name.includes('quantitative')) return '📊';
                  if (name.includes('qualitative')) return '💡';
                  if (name.includes('risk')) return '🛡️';
                  if (name.includes('synthesizer')) return '📝';
                  return '⚙️';
                };
                return (
                  <div key={agent} className={`agent-step ${status === 'running' ? 'active' : status === 'completed' ? 'done' : ''}`}>
                    <span className="agent-step-icon">{getIcon(agent)}</span>
                    <span>
                      {agent.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())} — {status as string}
                    </span>
                    <div className="agent-step-dot" />
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Error State */}
        {error && (
          <div className="error-card animate-fade-in">
            <div className="error-icon-wrapper">
              <svg className="error-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="10" />
                <line x1="12" y1="8" x2="12" y2="12" />
                <line x1="12" y1="16" x2="12.01" y2="16" />
              </svg>
            </div>
            <div className="error-details">
              <h3>Analysis Failed</h3>
              <p>{error}</p>
            </div>
          </div>
        )}

        {/* Analysis Results */}
        {!clarificationNeeded && !loading && (dashboardData ?? dummyAnalysisData) && (
          <AnalysisReport data={dashboardData ?? dummyAnalysisData} highlightedCards={highlightedCards} />
        )}

      </main>

      <ChatPanel
        chatHistory={chatHistory}
        loading={loading}
        clarificationNeeded={clarificationNeeded}
        clarificationCandidates={clarificationCandidates}
        clarificationMessage={clarificationMessage}
        onSubmit={submitQuery}
        onResolveClarification={resolveClarification}
        sessionId={sessionId}
      />
    </div>
  );
}

export default App;
