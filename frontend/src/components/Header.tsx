import React, { KeyboardEvent } from 'react';

interface HeaderProps {
  searchQuery: string;
  setSearchQuery: (query: string) => void;
  handleAnalyze: () => void;
  handleKeyPress: (e: KeyboardEvent<HTMLInputElement>) => void;
  loading: boolean;
}

const Header: React.FC<HeaderProps> = ({ searchQuery, setSearchQuery, handleAnalyze, handleKeyPress, loading }) => {
  return (
    <header className="app-header">
      <div className="header-logo">
        <svg className="logo-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path strokeLinecap="round" strokeLinejoin="round" d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
        </svg>
        <span className="logo-text">vittSarathi <span className="text-gradient">Analysis</span></span>
      </div>
      <div className="header-search">
        <div className="input-glow-wrapper header-glow-wrapper">
          <input
            type="text"
            placeholder="Enter ticker (e.g. TCS, RELIANCE)"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onKeyDown={handleKeyPress}
            className="search-input header-search-input"
            disabled={loading}
          />
          <button 
            onClick={handleAnalyze} 
            className="search-button header-search-button"
            disabled={loading || !searchQuery.trim()}
          >
            {loading ? (
              <span className="btn-spinner"></span>
            ) : (
              <>
                <svg className="search-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z" />
                </svg>
              </>
            )}
          </button>
        </div>
      </div>
    </header>
  );
};

export default Header;
