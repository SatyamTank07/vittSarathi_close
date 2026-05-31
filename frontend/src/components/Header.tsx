import React from 'react';

const Header: React.FC = () => {
  return (
    <header className="app-header">
      <div className="header-logo">
        <svg className="logo-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path strokeLinecap="round" strokeLinejoin="round" d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
        </svg>
        <span className="logo-text">vittSarathi <span className="text-gradient">Analysis</span></span>
      </div>
    </header>
  );
};

export default Header;
