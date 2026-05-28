import { useState, KeyboardEvent } from 'react';
import './App.css';
import Header from './components/Header';
import AnalysisSidebar from './components/AnalysisSidebar';
import AnalysisReport from './components/AnalysisReport';

function App() {
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [analysisData, setAnalysisData] = useState<any | null>(null);
  const [selectedReportId, setSelectedReportId] = useState<string | null>(null);
  const [refreshTrigger, setRefreshTrigger] = useState<number>(0);
  const [agentStep, setAgentStep] = useState<string>('idle');

  // Default quick tickers
  const quickTickers = [
    { label: 'TCS', ticker: 'TCS' },
    { label: 'Reliance', ticker: 'RELIANCE' },
    { label: 'HDFC Bank', ticker: 'HDFCBANK' },
    { label: 'Infosys', ticker: 'INFY' },
    { label: 'Apple', ticker: 'AAPL' },
  ];

  // Run Analysis
  const handleAnalyze = async (tickerOverride?: string) => {
    const symbol = (tickerOverride || searchQuery).trim().toUpperCase();
    if (!symbol) return;

    setLoading(true);
    setError(null);
    setAnalysisData(null);
    setSelectedReportId(null);
    setAgentStep('orchestrator');

    try {
      // Simulate agent progress for UX
      const progressTimer = setTimeout(() => setAgentStep('parallel'), 3000);
      const synthTimer = setTimeout(() => setAgentStep('synthesizer'), 15000);

      const response = await fetch(`http://localhost:8000/api/analyze/${encodeURIComponent(symbol)}`, {
        method: 'POST',
      });

      clearTimeout(progressTimer);
      clearTimeout(synthTimer);

      if (!response.ok) {
        const errData = await response.json();
        throw new Error(errData.detail || 'Analysis failed.');
      }

      const data = await response.json();
      setAnalysisData(data);
      setSelectedReportId(data.report_id);
      setRefreshTrigger(prev => prev + 1);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
      setAgentStep('idle');
    }
  };

  // Load a saved report
  const handleSelectReport = async (reportId: string) => {
    if (reportId === selectedReportId) return;

    setLoading(true);
    setError(null);

    try {
      const response = await fetch(`http://localhost:8000/api/reports/${reportId}`);
      if (!response.ok) throw new Error('Failed to load report.');

      const data = await response.json();
      setAnalysisData({
        ...data,
        final_thesis: data.report_markdown,
      });
      setSelectedReportId(reportId);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  // Handle report deletion
  const handleDeleteReport = (id: string) => {
    if (id === selectedReportId) {
      setAnalysisData(null);
      setSelectedReportId(null);
    }
  };

  const handleKeyPress = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      handleAnalyze();
    }
  };

  return (
    <div className="app-container">
      <Header
        searchQuery={searchQuery}
        setSearchQuery={setSearchQuery}
        handleAnalyze={() => handleAnalyze()}
        handleKeyPress={handleKeyPress}
        loading={loading}
      />

      {/* Report History Bar */}
      <AnalysisSidebar
        selectedReportId={selectedReportId}
        onSelectReport={handleSelectReport}
        onDeleteReport={handleDeleteReport}
        refreshTrigger={refreshTrigger}
      />

      {/* Main Content */}
      <main className="app-main-content">
        {/* Welcome State */}
        {!analysisData && !loading && !error && (
          <div className="welcome-section">
            <h1 className="search-title">Multi-Agent Stock Analysis</h1>
            <p className="search-subtitle">
              Enter a ticker symbol to run a deep fundamental analysis powered by 5 specialized AI agents — Orchestrator, Quantitative, Qualitative, Risk, and Synthesizer.
            </p>

            <div className="quick-tickers">
              <span className="quick-label">Quick analyze:</span>
              <div className="quick-tags">
                {quickTickers.map((item) => (
                  <button
                    key={item.ticker}
                    onClick={() => {
                      setSearchQuery(item.ticker);
                      handleAnalyze(item.ticker);
                    }}
                    className="quick-tag-btn"
                    disabled={loading}
                  >
                    {item.label} ({item.ticker})
                  </button>
                ))}
              </div>
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

        {/* Loading State — Agent Progress */}
        {loading && (
          <div className="analysis-loading animate-fade-in">
            <div className="analysis-spinner"></div>
            <h2>Analyzing...</h2>
            <p>5 AI agents are working in parallel</p>
            <div className="agent-progress">
              <div className={`agent-step ${agentStep === 'orchestrator' ? 'active' : agentStep !== 'idle' ? 'done' : ''}`}>
                <span className="agent-step-icon">🎯</span>
                <span>Orchestrator — Fetching data & classifying industry</span>
                <div className="agent-step-dot"></div>
              </div>
              <div className={`agent-step ${agentStep === 'parallel' ? 'active' : agentStep === 'synthesizer' ? 'done' : ''}`}>
                <span className="agent-step-icon">📊</span>
                <span>Quantitative Agent — Crunching numbers</span>
                <div className="agent-step-dot"></div>
              </div>
              <div className={`agent-step ${agentStep === 'parallel' ? 'active' : agentStep === 'synthesizer' ? 'done' : ''}`}>
                <span className="agent-step-icon">💡</span>
                <span>Qualitative Agent — Analyzing moat & strategy</span>
                <div className="agent-step-dot"></div>
              </div>
              <div className={`agent-step ${agentStep === 'parallel' ? 'active' : agentStep === 'synthesizer' ? 'done' : ''}`}>
                <span className="agent-step-icon">🛡️</span>
                <span>Risk Agent — Investigating red flags</span>
                <div className="agent-step-dot"></div>
              </div>
              <div className={`agent-step ${agentStep === 'synthesizer' ? 'active' : ''}`}>
                <span className="agent-step-icon">📝</span>
                <span>Synthesizer — Compiling investment thesis</span>
                <div className="agent-step-dot"></div>
              </div>
            </div>
          </div>
        )}

        {/* Analysis Results */}
        {analysisData && !loading && (
          <AnalysisReport data={analysisData} />
        )}
      </main>
    </div>
  );
}

export default App;
