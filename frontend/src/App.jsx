import { useState, useEffect } from 'react';
import './App.css';

function App() {
  const [isBackendOnline, setIsBackendOnline] = useState(false);
  const [checking, setChecking] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [stockData, setStockData] = useState(null);

  // Default quick tickers
  const quickTickers = [
    { label: 'Apple', ticker: 'AAPL' },
    { label: 'Nvidia', ticker: 'NVDA' },
    { label: 'Tesla', ticker: 'TSLA' },
    { label: 'Reliance', ticker: 'RELIANCE' },
    { label: 'TCS', ticker: 'TCS' },
    { label: 'Infosys', ticker: 'INFY' }
  ];

  // Check Backend Status
  useEffect(() => {
    let active = true;
    const checkBackend = async () => {
      try {
        const response = await fetch('http://localhost:8000/');
        if (response.ok) {
          const data = await response.json();
          if (active && data.status === 'running') {
            setIsBackendOnline(true);
            setChecking(false);
            return;
          }
        }
        throw new Error('Offline');
      } catch (err) {
        if (active) {
          setIsBackendOnline(false);
          setChecking(false);
        }
      }
    };
    checkBackend();
    const interval = setInterval(checkBackend, 5000);
    return () => {
      active = false;
      clearInterval(interval);
    };
  }, []);

  // Fetch Stock Data
  const handleSearch = async (tickerToSearch) => {
    const symbol = (tickerToSearch || searchQuery).trim().toUpperCase();
    if (!symbol) return;
    
    setLoading(true);
    setError(null);
    setStockData(null);

    try {
      const response = await fetch(`http://localhost:8000/api/stock/${encodeURIComponent(symbol)}`);
      if (!response.ok) {
        const errData = await response.json();
        throw new Error(errData.detail || 'Failed to fetch stock data.');
      }
      const data = await response.json();
      setStockData(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter') {
      handleSearch();
    }
  };

  // Helper formatting functions
  const formatCurrency = (val, currency = 'USD') => {
    if (val === null || val === undefined) return 'N/A';
    return new Intl.NumberFormat(currency === 'INR' ? 'en-IN' : 'en-US', {
      style: 'currency',
      currency: currency,
      maximumFractionDigits: 2
    }).format(val);
  };

  const formatCompact = (val, currency = null) => {
    if (val === null || val === undefined) return 'N/A';
    const options = {
      notation: 'compact',
      compactDisplay: 'short',
      maximumFractionDigits: 2
    };
    if (currency) {
      options.style = 'currency';
      options.currency = currency;
    }
    return new Intl.NumberFormat('en-US', options).format(val);
  };

  const formatPercentage = (val, isDecimal = true) => {
    if (val === null || val === undefined) return 'N/A';
    const pct = isDecimal ? val * 100 : val;
    return `${pct >= 0 ? '+' : ''}${pct.toFixed(2)}%`;
  };

  const formatNumber = (val) => {
    if (val === null || val === undefined) return 'N/A';
    return new Intl.NumberFormat('en-US').format(val);
  };

  // Recommendation Styling
  const getRecommendationBadge = (rec) => {
    if (!rec || rec === 'N/A') return <span className="badge badge-gray">N/A</span>;
    const cleanRec = rec.toLowerCase();
    if (cleanRec.includes('buy')) {
      return <span className="badge badge-green">{rec.toUpperCase().replace('_', ' ')}</span>;
    } else if (cleanRec.includes('sell')) {
      return <span className="badge badge-red">{rec.toUpperCase().replace('_', ' ')}</span>;
    } else {
      return <span className="badge badge-orange">{rec.toUpperCase().replace('_', ' ')}</span>;
    }
  };

  return (
    <div className="app-container">
      <div className="glow-orb glow-orb-1"></div>
      <div className="glow-orb glow-orb-2"></div>

      {/* Header */}
      <header className="app-header">
        <div className="header-logo">
          <svg className="logo-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path strokeLinecap="round" strokeLinejoin="round" d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
          </svg>
          <span className="logo-text">Ai Funda <span className="text-gradient">Stock</span></span>
        </div>
        <div className="pulse-indicator">
          <span className={`pulse-dot ${isBackendOnline ? 'online' : checking ? 'checking' : 'offline'}`}></span>
          <span className="pulse-text">
            {isBackendOnline ? 'Backend Connected' : checking ? 'Connecting...' : 'Backend Offline'}
          </span>
        </div>
      </header>

      {/* Main Layout */}
      <main className="app-main-content">
        <section className="search-section">
          <h1 className="search-title">Market Intelligence Dashboard</h1>
          <p className="search-subtitle">Fetch real-time financial metrics, risk assessment, and momentum stats instantly.</p>
          
          <div className="search-bar-container">
            <div className="input-glow-wrapper">
              <input
                type="text"
                placeholder="Enter stock symbol (e.g. AAPL, RELIANCE, TSLA)"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onKeyDown={handleKeyPress}
                className="search-input"
                disabled={loading}
              />
              <button 
                onClick={() => handleSearch()} 
                className="search-button"
                disabled={loading}
              >
                {loading ? (
                  <span className="btn-spinner"></span>
                ) : (
                  <>
                    <svg className="search-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <circle cx="11" cy="11" r="8" />
                      <line x1="21" y1="21" x2="16.65" y2="16.65" />
                    </svg>
                    <span>Analyze</span>
                  </>
                )}
              </button>
            </div>
            <p className="search-hint">
              * Note: Indian tickers are supported. Enter just the symbol (e.g., <strong>RELIANCE</strong> or <strong>TCS</strong>) and we will resolve it automatically!
            </p>
          </div>

          <div className="quick-tickers">
            <span className="quick-label">Popular searches:</span>
            <div className="quick-tags">
              {quickTickers.map((item) => (
                <button
                  key={item.ticker}
                  onClick={() => {
                    setSearchQuery(item.ticker);
                    handleSearch(item.ticker);
                  }}
                  className="quick-tag-btn"
                  disabled={loading}
                >
                  {item.label} ({item.ticker})
                </button>
              ))}
            </div>
          </div>
        </section>

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

        {/* Loading State Skeleton */}
        {loading && (
          <div className="skeleton-container animate-pulse">
            <div className="skeleton-hero"></div>
            <div className="skeleton-grid">
              {Array.from({ length: 12 }).map((_, index) => (
                <div key={index} className="skeleton-card"></div>
              ))}
            </div>
          </div>
        )}

        {/* Stock Details Dashboard */}
        {stockData && !loading && (
          <div className="dashboard-view animate-fade-in">
            {/* Hero Company Block */}
            <div className="company-hero-card">
              <div className="hero-top">
                <div className="hero-meta">
                  <div className="symbol-pill">{stockData.symbol}</div>
                  <h2 className="company-name">{stockData.longName}</h2>
                  <div className="sector-info">
                    <span className="sector-tag">{stockData.sector}</span>
                    <span className="industry-tag">{stockData.industry}</span>
                  </div>
                </div>
                <div className="price-container">
                  <div className="price-label">Current Price</div>
                  <div className="price-value">
                    {formatCurrency(stockData.currentPrice, stockData.currency)}
                  </div>
                  <div className="currency-badge">{stockData.currency}</div>
                </div>
              </div>
              {stockData.summary && (
                <div className="hero-summary">
                  <h4 className="summary-title">Business Summary</h4>
                  <p className="summary-text">{stockData.summary}</p>
                </div>
              )}
            </div>

            {/* Metrics Dashboard Grid */}
            <div className="metrics-grid">
              
              {/* 1. VALUATION */}
              <div className="metric-card">
                <div className="card-header">
                  <div className="card-icon valuation">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6" />
                    </svg>
                  </div>
                  <span className="card-title">Valuation</span>
                </div>
                <div className="card-body">
                  <div className="metric-value-row">
                    <span className="metric-label">P/E Ratio</span>
                    <span className="metric-value">{stockData.peRatio ? stockData.peRatio.toFixed(2) : 'N/A'}</span>
                  </div>
                  {stockData.peRatio && (
                    <div className="indicator-bar-container">
                      <div className={`indicator-bar-fill ${stockData.peRatio > 35 ? 'warning' : 'success'}`} style={{ width: `${Math.min(stockData.peRatio * 2, 100)}%` }}></div>
                    </div>
                  )}
                </div>
                <div className="card-footer">
                  <span className="info-icon">i</span>
                  <span className="why-matters">Shows if the stock is expensive or cheap relative to earnings.</span>
                </div>
              </div>

              {/* 2. GROWTH */}
              <div className="metric-card">
                <div className="card-header">
                  <div className="card-icon growth">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <line x1="18" y1="20" x2="18" y2="10" />
                      <line x1="12" y1="20" x2="12" y2="4" />
                      <line x1="6" y1="20" x2="6" y2="14" />
                    </svg>
                  </div>
                  <span className="card-title">Growth</span>
                </div>
                <div className="card-body">
                  <div className="metric-value-row">
                    <span className="metric-label">Revenue Growth</span>
                    <span className={`metric-value ${stockData.revenueGrowth >= 0 ? 'text-green' : 'text-red'}`}>
                      {formatPercentage(stockData.revenueGrowth, true)}
                    </span>
                  </div>
                  <div className="metric-value-row">
                    <span className="metric-label">Earnings Growth</span>
                    <span className={`metric-value ${stockData.earningsGrowth >= 0 ? 'text-green' : 'text-red'}`}>
                      {formatPercentage(stockData.earningsGrowth, true)}
                    </span>
                  </div>
                </div>
                <div className="card-footer">
                  <span className="info-icon">i</span>
                  <span className="why-matters">Tells whether the company is actually expanding.</span>
                </div>
              </div>

              {/* 3. PROFITABILITY */}
              <div className="metric-card">
                <div className="card-header">
                  <div className="card-icon profitability">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <circle cx="12" cy="12" r="10" />
                      <path d="M12 8v8M9 12h6" />
                    </svg>
                  </div>
                  <span className="card-title">Profitability</span>
                </div>
                <div className="card-body">
                  <div className="metric-value-row">
                    <span className="metric-label">Profit Margin</span>
                    <span className="metric-value">{formatPercentage(stockData.profitMargin, true)}</span>
                  </div>
                  <div className="metric-value-row">
                    <span className="metric-label">ROE</span>
                    <span className="metric-value">{formatPercentage(stockData.roe, true)}</span>
                  </div>
                  {stockData.profitMargin && (
                    <div className="indicator-bar-container">
                      <div className="indicator-bar-fill success" style={{ width: `${Math.min(Math.max(stockData.profitMargin * 100, 0), 100)}%` }}></div>
                    </div>
                  )}
                </div>
                <div className="card-footer">
                  <span className="info-icon">i</span>
                  <span className="why-matters">Measures how efficiently the business makes money.</span>
                </div>
              </div>

              {/* 4. FINANCIAL HEALTH */}
              <div className="metric-card">
                <div className="card-header">
                  <div className="card-icon health">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
                    </svg>
                  </div>
                  <span className="card-title">Financial Health</span>
                </div>
                <div className="card-body">
                  <div className="metric-value-row">
                    <span className="metric-label">Debt-to-Equity</span>
                    <span className={`metric-value ${stockData.debtToEquity > 150 ? 'text-red' : stockData.debtToEquity > 100 ? 'text-orange' : 'text-green'}`}>
                      {formatPercentage(stockData.debtToEquity, false)}
                    </span>
                  </div>
                  {stockData.debtToEquity && (
                    <div className="indicator-bar-container">
                      <div className={`indicator-bar-fill ${stockData.debtToEquity > 150 ? 'danger' : stockData.debtToEquity > 100 ? 'warning' : 'success'}`} style={{ width: `${Math.min(stockData.debtToEquity / 2, 100)}%` }}></div>
                    </div>
                  )}
                </div>
                <div className="card-footer">
                  <span className="info-icon">i</span>
                  <span className="why-matters">High debt can become dangerous in downturns.</span>
                </div>
              </div>

              {/* 5. MARKET SENTIMENT */}
              <div className="metric-card">
                <div className="card-header">
                  <div className="card-icon sentiment">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
                    </svg>
                  </div>
                  <span className="card-title">Market Sentiment</span>
                </div>
                <div className="card-body">
                  <div className="metric-value-row">
                    <span className="metric-label">Rating</span>
                    <span className="metric-value">{getRecommendationBadge(stockData.recommendation)}</span>
                  </div>
                  <div className="metric-value-row">
                    <span className="metric-label">Target Price</span>
                    <span className="metric-value text-cyan">
                      {formatCurrency(stockData.targetPrice, stockData.currency)}
                    </span>
                  </div>
                </div>
                <div className="card-footer">
                  <span className="info-icon">i</span>
                  <span className="why-matters">Shows Wall Street analyst expectations.</span>
                </div>
              </div>

              {/* 6. SHARE DATA */}
              <div className="metric-card">
                <div className="card-header">
                  <div className="card-icon shares">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <circle cx="18" cy="18" r="3" />
                      <circle cx="6" cy="6" r="3" />
                      <circle cx="6" cy="18" r="3" />
                      <path d="M20 4h2M4 20h2M12 4h2" />
                      <line x1="6" y1="9" x2="6" y2="15" />
                      <line x1="9" y1="6" x2="20" y2="6" />
                    </svg>
                  </div>
                  <span className="card-title">Share Data</span>
                </div>
                <div className="card-body">
                  <div className="metric-value-row">
                    <span className="metric-label">Market Cap</span>
                    <span className="metric-value text-cyan">{formatCompact(stockData.marketCap, stockData.currency)}</span>
                  </div>
                  <div className="metric-value-row">
                    <span className="metric-label">Shares Out</span>
                    <span className="metric-value">{formatCompact(stockData.sharesOutstanding)}</span>
                  </div>
                  <div className="metric-value-row">
                    <span className="metric-label">Float Shares</span>
                    <span className="metric-value">{formatCompact(stockData.floatShares)}</span>
                  </div>
                </div>
                <div className="card-footer">
                  <span className="info-icon">i</span>
                  <span className="why-matters">Helps judge company size and dilution risk.</span>
                </div>
              </div>

              {/* 7. TRADING ACTIVITY */}
              <div className="metric-card">
                <div className="card-header">
                  <div className="card-icon activity">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
                    </svg>
                  </div>
                  <span className="card-title">Trading Activity</span>
                </div>
                <div className="card-body">
                  <div className="metric-value-row">
                    <span className="metric-label">Volume</span>
                    <span className="metric-value">{formatNumber(stockData.volume)}</span>
                  </div>
                  <div className="metric-value-row">
                    <span className="metric-label">Avg Volume</span>
                    <span className="metric-value">{formatNumber(stockData.averageVolume)}</span>
                  </div>
                  {stockData.volume && stockData.averageVolume && (
                    <div className="indicator-bar-container">
                      <div className="indicator-bar-fill activity" style={{ width: `${Math.min((stockData.volume / stockData.averageVolume) * 50, 100)}%` }}></div>
                    </div>
                  )}
                </div>
                <div className="card-footer">
                  <span className="info-icon">i</span>
                  <span className="why-matters">Reveals liquidity and unusual activity.</span>
                </div>
              </div>

              {/* 8. RISK */}
              <div className="metric-card">
                <div className="card-header">
                  <div className="card-icon risk">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
                      <line x1="12" y1="9" x2="12" y2="13" />
                      <line x1="12" y1="17" x2="12.01" y2="17" />
                    </svg>
                  </div>
                  <span className="card-title">Risk</span>
                </div>
                <div className="card-body">
                  <div className="metric-value-row">
                    <span className="metric-label">Beta</span>
                    <span className={`metric-value ${stockData.beta > 1.5 ? 'text-red' : stockData.beta > 1 ? 'text-orange' : 'text-green'}`}>
                      {stockData.beta ? stockData.beta.toFixed(3) : 'N/A'}
                    </span>
                  </div>
                  <p className="card-sub-info">
                    {stockData.beta > 1 ? 'More volatile than market' : stockData.beta < 1 ? 'Less volatile than market' : 'Identical to market'}
                  </p>
                </div>
                <div className="card-footer">
                  <span className="info-icon">i</span>
                  <span className="why-matters">Indicates volatility compared to the market.</span>
                </div>
              </div>

              {/* 9. INCOME */}
              <div className="metric-card">
                <div className="card-header">
                  <div className="card-icon income">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <rect x="2" y="7" width="20" height="14" rx="2" ry="2" />
                      <path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16" />
                    </svg>
                  </div>
                  <span className="card-title">Income</span>
                </div>
                <div className="card-body">
                  <div className="metric-value-row">
                    <span className="metric-label">Div Yield</span>
                    <span className="metric-value text-green">{formatPercentage(stockData.dividendYield, false)}</span>
                  </div>
                  <div className="metric-value-row">
                    <span className="metric-label">Payout Ratio</span>
                    <span className="metric-value">{formatPercentage(stockData.payoutRatio, true)}</span>
                  </div>
                </div>
                <div className="card-footer">
                  <span className="info-icon">i</span>
                  <span className="why-matters">Important for income investors.</span>
                </div>
              </div>

              {/* 10. MOMENTUM */}
              <div className="metric-card">
                <div className="card-header">
                  <div className="card-icon momentum">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" />
                    </svg>
                  </div>
                  <span className="card-title">Momentum</span>
                </div>
                <div className="card-body">
                  <div className="momentum-row">
                    <div className="m-detail">
                      <span className="m-label">52W High</span>
                      <span className="m-val text-green">{formatCurrency(stockData.fiftyTwoWeekHigh, stockData.currency)}</span>
                    </div>
                    <div className="m-detail">
                      <span className="m-label">52W Low</span>
                      <span className="m-val text-red">{formatCurrency(stockData.fiftyTwoWeekLow, stockData.currency)}</span>
                    </div>
                  </div>
                  <div className="momentum-row separator-top">
                    <div className="m-detail">
                      <span className="m-label">50-Day MA</span>
                      <span className="m-val text-cyan">{formatCurrency(stockData.fiftyDayAverage, stockData.currency)}</span>
                    </div>
                    <div className="m-detail">
                      <span className="m-label">200-Day MA</span>
                      <span className="m-val text-purple">{formatCurrency(stockData.twoHundredDayAverage, stockData.currency)}</span>
                    </div>
                  </div>
                </div>
                <div className="card-footer">
                  <span className="info-icon">i</span>
                  <span className="why-matters">Helps understand trend and timing.</span>
                </div>
              </div>

              {/* 11. OWNERSHIP */}
              <div className="metric-card">
                <div className="card-header">
                  <div className="card-icon ownership">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
                      <circle cx="9" cy="7" r="4" />
                      <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
                      <path d="M16 3.13a4 4 0 0 1 0 7.75" />
                    </svg>
                  </div>
                  <span className="card-title">Ownership</span>
                </div>
                <div className="card-body">
                  <div className="metric-value-row">
                    <span className="metric-label">Institutional</span>
                    <span className="metric-value text-cyan">{formatPercentage(stockData.heldPercentInstitutions, true)}</span>
                  </div>
                  <div className="metric-value-row">
                    <span className="metric-label">Insider</span>
                    <span className="metric-value text-purple">{formatPercentage(stockData.heldPercentInsiders, true)}</span>
                  </div>
                </div>
                <div className="card-footer">
                  <span className="info-icon">i</span>
                  <span className="why-matters">Smart money and insider confidence.</span>
                </div>
              </div>

              {/* 12. CASH FLOW */}
              <div className="metric-card">
                <div className="card-header">
                  <div className="card-icon cashflow">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M12 1v22M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6" />
                    </svg>
                  </div>
                  <span className="card-title">Cash Flow</span>
                </div>
                <div className="card-body">
                  <div className="metric-value-row">
                    <span className="metric-label">Free Cash Flow</span>
                    <span className={`metric-value ${stockData.freeCashFlow >= 0 ? 'text-green' : stockData.freeCashFlow < 0 ? 'text-red' : ''}`}>
                      {formatCompact(stockData.freeCashFlow, stockData.currency)}
                    </span>
                  </div>
                  {stockData.freeCashFlow && (
                    <div className="indicator-bar-container">
                      <div className={`indicator-bar-fill ${stockData.freeCashFlow >= 0 ? 'success' : 'danger'}`} style={{ width: '100%' }}></div>
                    </div>
                  )}
                </div>
                <div className="card-footer">
                  <span className="info-icon">i</span>
                  <span className="why-matters">One of the strongest indicators of business quality.</span>
                </div>
              </div>

            </div>
          </div>
        )}
      </main>

      {/* Footer */}
      <footer className="app-footer-bar">
        <p>© 2026 Ai Funda - Intelligent Stock Analytics Dashboard</p>
      </footer>
    </div>
  );
}

export default App;
