import React from 'react';

interface HeaderProps {
  isOnline: boolean;
  onOpenLibrary: () => void;
}

const Header: React.FC<HeaderProps> = ({ isOnline, onOpenLibrary }) => {
  return (
    <header className="app-header" style={{ justifyContent: 'space-between' }}>
      <div className="header-logo">
        <svg className="logo-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path strokeLinecap="round" strokeLinejoin="round" d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
        </svg>
        <span className="logo-text">vittSarathi <span className="text-gradient">Analysis</span></span>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
        <button 
          onClick={onOpenLibrary}
          style={{
            background: 'none',
            border: '1px solid var(--border)',
            color: 'var(--text-main)',
            cursor: 'pointer',
            padding: '6px 12px',
            borderRadius: '6px',
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            fontSize: '13px',
            fontFamily: 'var(--font-sans)',
            transition: 'background 0.2s'
          }}
          onMouseOver={(e) => e.currentTarget.style.background = 'var(--bg-card-hover)'}
          onMouseOut={(e) => e.currentTarget.style.background = 'none'}
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path strokeLinecap="round" strokeLinejoin="round" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
          </svg>
          Library
        </button>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <div 
            style={{ 
              width: '8px', 
              height: '8px', 
              borderRadius: '50%', 
              backgroundColor: isOnline ? '#22c55e' : '#ef4444',
              animation: isOnline ? 'pulseStatus 2s infinite' : 'none'
            }} 
          />
          <span style={{ fontSize: '12px', color: isOnline ? '#22c55e' : '#9ca3af' }}>
            {isOnline ? 'Live' : 'Offline'}
          </span>
        </div>
      </div>
    </header>
  );
};

export default Header;
