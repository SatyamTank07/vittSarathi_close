import React, { useState, useRef, useEffect } from 'react';

interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
}

interface ChatSession {
  id: string;
  title: string;
  created_at: string;
}

const ChatSidebar = () => {
  const [messages, setMessages] = useState<Message[]>([
    { id: '1', role: 'system', content: 'Chat interface connected. Ask about stocks!' }
  ]);
  const [inputText, setInputText] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [sessionToDelete, setSessionToDelete] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const [isSidebarOpen, setIsSidebarOpen] = useState(false);

  const fetchSessions = async () => {
    try {
      const res = await fetch('http://localhost:8000/api/chat/sessions');
      if (res.ok) {
        const data = await res.json();
        setSessions(data);
      }
    } catch (error) {
      console.error('Failed to fetch sessions:', error);
    }
  };

  useEffect(() => {
    fetchSessions();
  }, []);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleNewChat = () => {
    setSessionId(null);
    setMessages([
      { id: Date.now().toString(), role: 'system', content: 'New chat session started. Ask about stocks!' }
    ]);
    setIsSidebarOpen(false); // Automatically close the sidebar to show the new chat UI
  };

  const handleSelectSession = async (id: string) => {
    if (id === sessionId) {
      setIsSidebarOpen(false);
      return;
    }
    setSessionId(id);
    setIsLoading(true);
    setMessages([]);
    setIsSidebarOpen(false); // Auto-close sidebar on mobile/selection if desired
    
    try {
      const res = await fetch(`http://localhost:8000/api/chat/sessions/${id}/messages`);
      if (res.ok) {
        const data = await res.json();
        if (data.length === 0) {
           setMessages([{ id: Date.now().toString(), role: 'system', content: 'Chat interface connected. Ask about stocks!' }]);
        } else {
           setMessages(data);
        }
      }
    } catch (error) {
      console.error('Failed to load session messages:', error);
      setMessages([{ id: Date.now().toString(), role: 'system', content: 'Failed to load messages.' }]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleDeleteSession = (id: string, e: React.MouseEvent) => {
    e.stopPropagation(); // Prevent triggering handleSelectSession
    setSessionToDelete(id);
  };

  const confirmDeleteSession = async () => {
    if (!sessionToDelete) return;
    
    try {
      const res = await fetch(`http://localhost:8000/api/chat/sessions/${sessionToDelete}`, {
        method: 'DELETE',
      });
      
      if (res.ok) {
        setSessions(prev => {
          const newSessions = prev.filter(session => session.id !== sessionToDelete);
          
          if (newSessions.length === 0) {
            handleNewChat();
            setIsSidebarOpen(false);
          } else if (sessionToDelete === sessionId) {
            handleNewChat();
          }
          
          return newSessions;
        });
      } else {
        console.error('Failed to delete session');
      }
    } catch (error) {
      console.error('Error deleting session:', error);
    } finally {
      setSessionToDelete(null);
    }
  };

  const handleSend = async () => {
    if (!inputText.trim()) return;
    
    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: inputText
    };
    
    setMessages(prev => [...prev, userMessage]);
    setInputText('');
    setIsLoading(true);

    try {
      let currentSessionId = sessionId;
      
      // Create session if it doesn't exist
      if (!currentSessionId) {
        const sessionRes = await fetch('http://localhost:8000/api/chat/sessions', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ title: userMessage.content.substring(0, 30) + '...' })
        });
        if (!sessionRes.ok) throw new Error('Failed to create session');
        const sessionData = await sessionRes.json();
        currentSessionId = sessionData.id;
        setSessionId(currentSessionId);
        
        // Refresh the sessions list to show the new chat
        fetchSessions();
      }

      // Send message
      const msgRes = await fetch(`http://localhost:8000/api/chat/sessions/${currentSessionId}/message`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: userMessage.content })
      });
      
      if (!msgRes.ok) throw new Error('Failed to send message');
      
      const msgData = await msgRes.json();
      setMessages(prev => [...prev, {
        id: msgData.id,
        role: msgData.role,
        content: msgData.content
      }]);
      
    } catch (error) {
      console.error(error);
      setMessages(prev => [...prev, {
        id: Date.now().toString(),
        role: 'system',
        content: 'Failed to communicate with AI. Is the backend running and API key set?'
      }]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <aside className="chat-section">
      <div className="chat-header">
        <button 
          onClick={() => setIsSidebarOpen(!isSidebarOpen)}
          style={{ background: 'transparent', border: 'none', color: 'var(--text-main)', fontSize: '1.25rem', cursor: 'pointer', padding: '0.2rem', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
          title="Toggle Chat History"
        >
          ☰
        </button>
        <button className="new-chat-btn" onClick={handleNewChat}>New Chat</button>
      </div>
      <div className="chat-layout">
        {isSidebarOpen ? (
          <div className="chat-history" style={{ width: '100%' }}>
            {sessions.map(session => (
              <div 
                key={session.id} 
                className={`chat-session-item ${session.id === sessionId ? 'active' : ''}`}
                onClick={() => handleSelectSession(session.id)}
              >
                <div className="chat-session-content">
                  <div className="chat-session-title">{session.title}</div>
                  <div className="chat-session-date">{new Date(session.created_at).toLocaleDateString()}</div>
                </div>
                <button 
                  className="delete-session-btn"
                  onClick={(e) => handleDeleteSession(session.id, e)}
                  title="Delete Session"
                >
                  ×
                </button>
              </div>
            ))}
          </div>
        ) : (
          <div className="chat-messages-container">
            <div className="chat-messages">
              {messages.map(msg => (
                <div key={msg.id} className={`chat-message ${msg.role}`}>
                  {msg.content}
                </div>
              ))}
              {isLoading && (
                <div className="chat-message assistant">
                  <div className="btn-spinner" style={{ width: '16px', height: '16px', borderColor: 'rgba(147, 51, 234, 0.2)', borderTopColor: 'var(--primary)' }}></div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>
            <div className="chat-input-wrapper">
              <input 
                type="text" 
                placeholder="Ask about stocks..." 
                className="chat-input"
                value={inputText}
                onChange={(e) => setInputText(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleSend()}
                disabled={isLoading}
              />
              <button 
                className="chat-send-btn" 
                onClick={handleSend}
                disabled={isLoading || !inputText.trim()}
              >
                Send
              </button>
            </div>
          </div>
        )}
      </div>

      {sessionToDelete && (
        <div className="delete-modal-overlay">
          <div className="delete-modal">
            <h3>Delete Chat Session</h3>
            <p>Are you sure you want to delete this chat? This action cannot be undone.</p>
            <div className="modal-actions">
              <button className="btn-cancel" onClick={() => setSessionToDelete(null)}>Cancel</button>
              <button className="btn-danger" onClick={confirmDeleteSession}>Delete</button>
            </div>
          </div>
        </div>
      )}
    </aside>
  );
};

export default ChatSidebar;
