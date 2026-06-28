import React, { KeyboardEvent } from 'react';

interface ChatBarProps {
  value: string;
  onChange: (val: string) => void;
  onSubmit: () => void;
  loading: boolean;
  disabled?: boolean;
  placeholder?: string;
  onPinClick?: () => void;
}

const ChatBar: React.FC<ChatBarProps> = ({
  value,
  onChange,
  onSubmit,
  loading,
  disabled = false,
  placeholder = "Ask about any stock... e.g. 'Analyze RELIANCE'",
  onPinClick,
}) => {
  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !loading && !disabled && value.trim()) {
      onSubmit();
    }
  };

  return (
    <div className="chat-bar-fixed">
      <div className="chat-bar-wrapper">
        <div className="chat-bar-glass">
          {onPinClick && (
            <button
              className="chat-pin-btn"
              onClick={onPinClick}
              disabled={loading || disabled}
              title="Upload Document"
            >
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" />
              </svg>
            </button>
          )}
          <input
            type="text"
            className="chat-bar-input"
            placeholder={placeholder}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={loading || disabled}
          />
          <button
            className="chat-bar-btn"
            onClick={onSubmit}
            disabled={loading || disabled || !value.trim()}
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
