import React from 'react';

const ChatSidebar = () => {
  return (
    <aside className="chat-section">
      <div className="chat-header">
        <h3>AI Assistant</h3>
      </div>
      <div className="chat-messages">
        <div className="chat-message system">
          Chat interface will be implemented here.
        </div>
      </div>
      <div className="chat-input-wrapper">
        <input type="text" placeholder="Ask about stocks..." className="chat-input" disabled />
        <button className="chat-send-btn" disabled>Send</button>
      </div>
    </aside>
  );
};

export default ChatSidebar;
