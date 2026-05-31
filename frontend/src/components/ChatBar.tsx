import React, { KeyboardEvent } from 'react';

interface ChatBarProps {
  value: string;
  onChange: (val: string) => void;
  onSubmit: () => void;
  loading: boolean;
  placeholder?: string;
}

const ChatBar: React.FC<ChatBarProps> = ({
  value,
  onChange,
  onSubmit,
  loading,
  placeholder = "Ask about any stock... e.g. 'Analyze RELIANCE'",
}) => {
  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !loading && value.trim()) {
      onSubmit();
    }
  };

  return (
    <div className="chat-bar-fixed">
      <div className="chat-bar-wrapper">
        <div className="chat-bar-glass">
          <input
            type="text"
            className="chat-bar-input"
            placeholder={placeholder}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={loading}
          />
          <button
            className="chat-bar-btn"
            onClick={onSubmit}
            disabled={loading || !value.trim()}
          >
            {loading ? (
              <span className="btn-spinner" />
            ) : (
              <>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <line x1="22" y1="2" x2="11" y2="13" />
                  <polygon points="22 2 15 22 11 13 2 9 22 2" />
                </svg>
                Analyze
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
};

export default ChatBar;
