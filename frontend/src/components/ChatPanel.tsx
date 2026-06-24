import React, { useState, useRef, useEffect } from 'react';
import ChatBar from './ChatBar';

interface ChatPanelProps {
  chatHistory: Array<{
    role: 'user' | 'assistant';
    content: string;
    type?: 'chat' | 'patch_confirm';
  }>;
  loading: boolean;
  clarificationNeeded: boolean;
  clarificationCandidates: Array<{ ticker: string; company_name: string }>;
  clarificationMessage: string;
  onSubmit: (query: string) => void;
  onResolveClarification: (ticker: string, companyName: string) => void;
  sessionId: string | null;
}

const ChatPanel: React.FC<ChatPanelProps> = ({
  chatHistory,
  loading,
  clarificationNeeded,
  clarificationCandidates,
  clarificationMessage,
  onSubmit,
  onResolveClarification,
  sessionId
}) => {
  const [inputValue, setInputValue] = useState('');
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chatHistory.length, loading, clarificationNeeded]);

  const handleSubmit = () => {
    if (!inputValue.trim() || loading) return;
    onSubmit(inputValue);
    setInputValue('');
  };

  const hasMessages = chatHistory.length > 0 || loading || clarificationNeeded;

  return (
    <div className={`chat-panel-fixed ${hasMessages ? 'expanded' : ''}`}>
      <div className="chat-panel-container">
        <div className="chat-panel-header">
          <span>Conversation</span>
          <div className={`chat-panel-session-dot ${sessionId ? 'active' : ''}`} />
        </div>

        <div className="chat-panel-messages">
          {chatHistory.map((msg, idx) => {
            if (msg.role === 'user') {
              return (
                <div key={idx} className="chat-bubble chat-bubble-user">
                  {msg.content}
                </div>
              );
            } else {
              if (msg.type === 'patch_confirm') {
                return (
                  <div key={idx} className="chat-bubble chat-bubble-patch">
                    ✓ Dashboard updated — {msg.content}
                  </div>
                );
              } else {
                return (
                  <div key={idx} className="chat-bubble chat-bubble-assistant">
                    <div className="chat-bubble-label">VittSarathi</div>
                    {msg.content}
                  </div>
                );
              }
            }
          })}
          
          {clarificationNeeded && (
            <div className="chat-bubble chat-bubble-assistant chat-bubble-clarification">
              <div className="chat-bubble-label">VittSarathi</div>
              <p className="chat-clarification-message">{clarificationMessage}</p>

              {clarificationCandidates.length > 0 ? (
                <>
                  <p className="chat-clarification-hint">Tap a company to continue:</p>
                  <div className="chat-clarification-options">
                    {clarificationCandidates.map((c, idx) => (
                      <button
                        key={idx}
                        className="chat-clarification-btn"
                        onClick={() => onResolveClarification(c.ticker, c.company_name)}
                        disabled={loading}
                      >
                        <span className="chat-clarification-company">{c.company_name}</span>
                        <span className="chat-clarification-ticker">{c.ticker}</span>
                      </button>
                    ))}
                  </div>
                </>
              ) : (
                <p className="chat-clarification-hint">
                  Please try again with a more specific company name or ticker.
                </p>
              )}
            </div>
          )}

          {loading && (
            <div className="chat-bubble chat-bubble-assistant">
              <span className="chat-typing-dot" />
              <span className="chat-typing-dot" />
              <span className="chat-typing-dot" />
            </div>
          )}
          
          <div ref={bottomRef} />
        </div>
        
        <div className="chat-panel-input-row">
          <ChatBar 
            value={inputValue}
            onChange={setInputValue}
            onSubmit={handleSubmit}
            loading={loading}
          />
        </div>
      </div>
    </div>
  );
};

export default ChatPanel;
