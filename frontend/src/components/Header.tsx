import React, { KeyboardEvent } from 'react';

interface HeaderProps {
  searchQuery: string;
  setSearchQuery: (query: string) => void;
  handleSearch: () => void;
  handleKeyPress: (e: KeyboardEvent<HTMLInputElement>) => void;
  loading: boolean;
}

const Header: React.FC<HeaderProps> = ({ searchQuery, setSearchQuery, handleSearch, handleKeyPress, loading }) => {
  return (
    <header className="app-header">
      <div className="header-logo">
        <svg className="logo-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path strokeLinecap="round" strokeLinejoin="round" d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
        </svg>
        <span className="logo-text">Ai Funda <span className="text-gradient">Stock</span></span>
      </div>
      <div className="header-search">
        <div className="input-glow-wrapper header-glow-wrapper">
          <input
            type="text"
            placeholder="Search symbol (e.g. AAPL)"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onKeyDown={handleKeyPress}
            className="search-input header-search-input"
            disabled={loading}
          />
          <button 
            onClick={() => handleSearch()} 
            className="search-button header-search-button"
            disabled={loading}
          >
            {loading ? (
              <span className="btn-spinner"></span>
            ) : (
              <svg className="search-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="11" cy="11" r="8" />
                <line x1="21" y1="21" x2="16.65" y2="16.65" />
              </svg>
            )}
          </button>
        </div>
      </div>
    </header>
  );
};

export default Header;
